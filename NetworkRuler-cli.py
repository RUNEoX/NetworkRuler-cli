import argparse
import psutil
import subprocess
import os
import time
import pydivert
import ctypes
import sys
from datetime import datetime
import subprocess
import pydivert

ctypes.WinDLL(r"A:\Program\NetworkRuler-cli\WinDivert-2.2.2-A\WinDivert64.dll")

def list_all():
    seen = set()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            print(f"{proc.info['pid']:<10} {proc.info['name']}")
            seen.add(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    print("\n[Services]:")
    output = subprocess.check_output('sc query type= service state= all', shell=True)
    lines = output.decode().splitlines()
    for line in lines:
        if "SERVICE_NAME" in line:
            print(line.strip().split(":")[-1].strip())

def list_apps():
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            print(f"{proc.info['pid']:<10} {proc.info['name']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

def list_services():
    output = subprocess.check_output('sc query type= service state= all', shell=True)
    lines = output.decode().splitlines()
    for line in lines:
        if "SERVICE_NAME" in line:
            print(line.strip().split(":")[-1].strip())

def kill_process(name_or_pid):
    # Handle both PID and name as inputs
    for proc in psutil.process_iter(['pid', 'name']):
        if str(proc.info['pid']) == str(name_or_pid) or proc.info['name'].lower() == str(name_or_pid).lower():
            try:
                proc.kill()
                print(f"Killed {proc.info['name']} (PID: {proc.info['pid']})")
                return
            except Exception as e:
                print(f"Failed: {e}")
                return
    try:
        subprocess.run(f'sc stop "{name_or_pid}"', shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Stopped service: {name_or_pid}")
    except subprocess.CalledProcessError:
        print("No such process or service found.")

def get_target_ips(proc_name):
    target_ips = set()
    for conn in psutil.net_connections(kind='inet'):
        try:
            if conn.pid:
                p = psutil.Process(conn.pid)
                if p.name().lower() == proc_name.lower() and conn.raddr:
                    target_ips.add(conn.raddr.ip)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return target_ips

def throttle_process(proc_name, mbps):
    max_bps = mbps * 1024 * 1024 // 8
    print(f"Throttling {proc_name} to {mbps} Mbps")
    sent = 0
    start_time = time.time()
    ip_cache = set()

    with pydivert.WinDivert("outbound and tcp") as w:
        for packet in w:
            now = time.time()
            if now - start_time >= 1:
                start_time = now
                sent = 0
                ip_cache = get_target_ips(proc_name)

            if packet.dst_addr in ip_cache:
                if sent + len(packet.payload) > max_bps:
                    continue
                else:
                    sent += len(packet.payload)
                    w.send(packet)
            else:
                w.send(packet)

def throttle_background_apps(mbps):
    max_bps = mbps * 1024 * 1024 // 8
    bg_procs = []
    for proc in psutil.process_iter(['pid', 'name', 'username']):
        try:
            if not proc.name().lower().endswith('system') and not proc.username() == os.getlogin():
                continue
            if not proc.name().endswith('.exe'):
                continue
            if not proc.name().lower() in ("explorer.exe", "cmd.exe"):
                bg_procs.append(proc.name().lower())
        except:
            continue
    bg_procs = list(set(bg_procs))

    print(f"Throttling background apps ({len(bg_procs)} found) to {mbps} Mbps")
    sent = 0
    start_time = time.time()
    ip_map = {}

    with pydivert.WinDivert("outbound and tcp") as w:
        for packet in w:
            now = time.time()
            if now - start_time >= 1:
                start_time = now
                sent = 0
                ip_map = {}
                for name in bg_procs:
                    for conn in psutil.net_connections(kind='inet'):
                        try:
                            if conn.pid:
                                p = psutil.Process(conn.pid)
                                if p.name().lower() == name and conn.raddr:
                                    ip_map.setdefault(name, set()).add(conn.raddr.ip)
                        except:
                            continue

            match = any(packet.dst_addr in ip_map.get(name, set()) for name in bg_procs)
            if match:
                if sent + len(packet.payload) > max_bps:
                    continue
                else:
                    sent += len(packet.payload)
                    w.send(packet)
            else:
                w.send(packet)

def schedule_throttle(proc_name, mbps, start_time, end_time):
    now = datetime.now().time()
    if start_time <= now <= end_time:
        throttle_process(proc_name, mbps)

def monitor_bandwidth():
    print("Real-time Bandwidth Monitor:")
    while True:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                net = proc.connections(kind='inet')
                total_sent = total_recv = 0
                for conn in net:
                    total_sent += conn.sent_bytes
                    total_recv += conn.recv_bytes
                print(f"{proc.info['name']} (PID: {proc.info['pid']}): Sent={total_sent} Recv={total_recv}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(1)

def save_profile(profile_name, settings):
    with open(f"{profile_name}.profile", 'w') as file:
        file.write(str(settings))
    print(f"Profile {profile_name} saved.")

def load_profile(profile_name):
    if os.path.exists(f"{profile_name}.profile"):
        with open(f"{profile_name}.profile", 'r') as file:
            settings = eval(file.read())
        print(f"Profile {profile_name} loaded.")
        return settings
    else:
        print("Profile does not exist.")
        return {}

def stealth_mode():
    ctypes.windll.kernel32.FreeConsole()

def log_activity(log_file, activity):
    with open(log_file, 'a') as file:
        file.write(f"{datetime.now()} - {activity}\n")
    print(f"Activity logged to {log_file}.")

def show_help():
    help_text = """
Usage: network ruler <command> [options]

Available Commands:
  --list                          List all processes and services
  app --list                      List only applications
  srv --list                      List only services
  --kill <name|pid>              Kill a process or stop a service
  --limit <process.exe> <speed>  Throttle specific process (ex: 5mb)
  background app --limit <speed> Throttle all background apps (ex: 1mb)
  monitor --live                 Monitor real-time bandwidth usage
  save <profile_name> <settings>  Save current settings to profile
  load <profile_name>            Load settings from a profile
  stealth                        Run in background with no terminal window
  log <file> <activity>          Log network activity

Examples:
  network ruler --list
  network ruler app --list
  network ruler srv --list
  network ruler --kill explorer.exe
  network ruler --limit fdm.exe 5mb
  network ruler background app --limit 1mb
  network ruler monitor --live
  network ruler save gaming_profile {"limit": "5mb"}
  network ruler stealth
"""
    print(help_text)

def main():
    if sys.argv[0] == 'nr':
        sys.argv[0] = 'network ruler'

    if '--help' in sys.argv:
        show_help()
        return

    if len(sys.argv) < 2:
        print("Missing command, honey. Use --help 💋")
        return

    if sys.argv[1] == '--list':
        list_all()
    elif sys.argv[1] == '--kill':
        if len(sys.argv) >= 3:
            kill_process(sys.argv[2])
        else:
            print("Missing target to kill")
    elif sys.argv[1] == '--limit':
        if len(sys.argv) >= 4:
            mb = int(sys.argv[3].lower().replace('mb', '').replace('m', ''))
            throttle_process(sys.argv[2], mb)
        else:
            print("Usage: --limit <proc.exe> 5mb")
    elif sys.argv[1] == 'app' and sys.argv[2] == '--list':
        list_apps()
    elif sys.argv[1] == 'srv' and sys.argv[2] == '--list':
        list_services()
    elif sys.argv[1] == 'background' and sys.argv[2] == 'app' and sys.argv[3] == '--limit':
        if len(sys.argv) >= 5:
            mb = int(sys.argv[4].lower().replace('mb', '').replace('m', ''))
            throttle_background_apps(mb)
        else:
            print("Usage: background app --limit 1mb")
    elif sys.argv[1] == 'monitor' and sys.argv[2] == '--live':
        monitor_bandwidth()
    elif sys.argv[1] == 'save':
        if len(sys.argv) >= 4:
            save_profile(sys.argv[2], sys.argv[3])
        else:
            print("Usage: save <profile_name> <settings>")
    elif sys.argv[1] == 'load':
        if len(sys.argv) >= 3:
            load_profile(sys.argv[2])
        else:
            print("Usage: load <profile_name>")
    elif sys.argv[1] == 'stealth':
        stealth_mode()
    elif sys.argv[1] == 'log':
        if len(sys.argv) >= 4:
            log_activity(sys.argv[2], sys.argv[3])
        else:
            print("Usage: log <file> <activity>")
    else:
        print("Unknown command. Use --help")

if __name__ == '__main__':
    if os.name != 'nt':
        print("only works on Windows.")
    elif not ctypes.windll.shell32.IsUserAnAdmin():
        print("Run as admin")
    else:
        main()

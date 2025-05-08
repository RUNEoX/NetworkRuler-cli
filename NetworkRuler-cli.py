import argparse
import psutil
import subprocess
import os
import time
import ctypes
import sys
from datetime import datetime

def add_to_path(new_path):
    current_path = os.environ.get("PATH", "")
    if new_path not in current_path:
        os.environ["PATH"] = current_path + os.pathsep + new_path
        print(f"Added {new_path} to PATH.")

def install_path():
    new_path = r'C:\your\fixed\path\here'  
    add_to_path(new_path)

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
    killed_any = False
    for proc in psutil.process_iter(['pid', 'name']):
        if str(proc.info['pid']) == str(name_or_pid) or proc.info['name'].lower() == str(name_or_pid).lower():
            try:
                proc.kill()
                print(f"Killed {proc.info['name']} (PID: {proc.info['pid']})")
                killed_any = True
            except Exception as e:
                print(f"Failed: {e}")

    if not killed_any:
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
    exe_path = None
    for proc in psutil.process_iter(['pid', 'name', 'exe']):
        if proc.info['name'].lower() == proc_name.lower():
            exe_path = proc.info['exe']
            break

    if not exe_path:
        print(f"Could not find process: {proc_name}")
        return

    rule_name = f"NR_{proc_name}_{mbps}mb"
    bps = mbps * 1024 * 1024  # Convert Mbps to bits per second

    ps_cmd = (
        f"New-NetQosPolicy -Name '{rule_name}' -AppPath '{exe_path}' "
        f"-ThrottleRateActionBitsPerSecond {bps} -PolicyStore ActiveStore"
    )

    try:
        subprocess.run(["powershell", "-Command", ps_cmd], check=True)
        print(f"Throttling {proc_name} to {mbps} Mbps using New-NetQosPolicy")  # Throttle bandwidth dont work for now 
    except subprocess.CalledProcessError as e:
        print("Failed to set throttle rule:", e)

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

    for packet in psutil.net_connections(kind='inet'):
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

def schedule_throttle(proc_name, mbps, start_time, end_time):
    now = datetime.now().time()
    if start_time <= now <= end_time:
        throttle_process(proc_name, mbps)

def monitor_bandwidth():
    print("Real-time Bandwidth Monitor (Press Ctrl+C to quit):")
    previous_sent = psutil.net_io_counters().bytes_sent
    previous_recv = psutil.net_io_counters().bytes_recv

    try:
        while True:
            time.sleep(1)

            current_sent = psutil.net_io_counters().bytes_sent
            current_recv = psutil.net_io_counters().bytes_recv

            sent_delta = current_sent - previous_sent
            recv_delta = current_recv - previous_recv

            print(f"Sent: {sent_delta / (1024 * 1024):.2f} MB/s | Received: {recv_delta / (1024 * 1024):.2f} MB/s")

            previous_sent = current_sent
            previous_recv = current_recv
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")

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

    For alias:
    (if the alias dont  work )
    put the network_ruler.bat + network_ruler.ps1 file in the System PATH 
    it will work from any directory as "nr" command
    no need for cd "directory" to run the script
    Example: nr --list
    """
    
    print(help_text)

def main():
    install_path()

    if sys.argv[0] == 'nr':
        sys.argv[0] = 'network ruler'

    if '--help' in sys.argv:
        show_help()
        return

    if len(sys.argv) < 2:
        print("Missing command, honey. Use --help ")
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
            throttle_process(sys.argv[2], mb)  # Throttle bandwidth dont work for now
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
    else:
        print("Unknown command, sweetheart! Use --help for options.")

if __name__ == '__main__':
    main()

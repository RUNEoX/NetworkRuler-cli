import argparse
import psutil
import subprocess
import os
import time
import ctypes
import sys
from datetime import datetime
import json
from pathlib import Path

command_history = []

def add_to_path(new_path):
    current_path = os.environ.get("PATH", "")
    if new_path not in current_path:
        os.environ["PATH"] = current_path + os.pathsep + new_path
        print(f"Added {new_path} to PATH.")

ALIAS_FILE = Path(__file__).parent / "aliases.json"

def load_aliases():
    if ALIAS_FILE.exists():
        with open(ALIAS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_aliases(aliases):
    with open(ALIAS_FILE, 'w') as f:
        json.dump(aliases, f)

def resolve_alias(args):
    aliases = load_aliases()
    combined = ' '.join(args)
    for real, alias in aliases.items():
        if ' '.join(args) == alias:
            return real.split()
    return args

def set_alias(real, alias):
    aliases = load_aliases()
    aliases[real] = alias
    save_aliases(aliases)
    print(f"Alias set: '{alias}' -> '{real}'")
    
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

def list_apps(prefix=None):
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            name = proc.info['name']
            if prefix is None or name.lower().startswith(prefix.lower()):
                print(f"{proc.info['pid']:<10} {name}")
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
    profile_dir = "profiles"
    os.makedirs(profile_dir, exist_ok=True)
    
    profile_path = os.path.join(profile_dir, f"{profile_name}.json")
    profile_data = {
        "profile_name": profile_name,
        "settings": settings,
        "commands": command_history
    }

    with open(profile_path, "w") as profile_file:
        json.dump(profile_data, profile_file)
    
    print(f"Profile '{profile_name}' saved successfully.")

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

def install_path():
    username = os.getlogin()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    current_user_path = os.environ.get("PATH", "")

    if script_dir not in current_user_path:
        try:
            subprocess.run([
                "powershell",
                "-Command",
                f"[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH', 'User') + ';{script_dir}', 'User')"
            ], check=True)
            print(f"Added {script_dir} to PATH for user: {username}")
        except subprocess.CalledProcessError:
            print(f"\n❌ Auto-adding to PATH failed, sugar. You might not have permission.\n👉 Run this manually in PowerShell:\n")
            print(f"manual_add_to_path('{script_dir}')\n")


def manual_add_to_path(path=None):
    if path is None:
        path = os.path.dirname(os.path.abspath(__file__))

    try:
        subprocess.run([
            "powershell",
            "-Command",
            f"[Environment]::SetEnvironmentVariable('PATH', [Environment]::GetEnvironmentVariable('PATH', 'User') + ';{path}', 'User')"
        ], check=True)
        print(f"✅ Manually added {path} to PATH.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Manual add failed too, daddy... Error: {e}")

def run_cmd(title, command):
    try:
        output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True)
        print(f"\n✅ {title}:\n{output}")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Failed to run {title}:\n{e.output}")

def handle_net_commands(args):
    cmd_map = {
        ('-f', 'dns'): ("Flush DNS", "ipconfig /flushdns"),
        ('-r', 'dns'): ("Register DNS", "ipconfig /registerdns"),
        ('-d', 'ip'): ("Release IP", "ipconfig /release"),
        ('-renew', 'ip'): ("Renew IP", "ipconfig /renew"),
        ('-s', 'config'): ("IP Configuration (All)", "ipconfig /all"),
        ('-s', 'interfaces'): ("Active IP Interfaces", "ipconfig"),
        ('-show', 'firewall'): ("Show Firewall Status", "netsh advfirewall show allprofiles"),
        ('-reset', 'firewall'): ("Reset Firewall", "netsh advfirewall reset"),
        ('-on', 'firewall'): ("Enable Firewall", "netsh advfirewall set allprofiles state on"),
        ('-off', 'firewall'): ("Disable Firewall", "netsh advfirewall set allprofiles state off"),
        ('-s', 'interfaces', 'netsh'): ("Netsh Interfaces", "netsh interface show interface"),
        ('-s', 'address'): ("Show IP Addresses", "netsh interface ip show addresses"),
        ('-reset', 'winsock'): ("Reset Winsock", "netsh winsock reset"),
        ('-reset', 'tcp'): ("Reset TCP/IP Stack", "netsh int ip reset"),
        ('-reset', 'proxy'): ("Reset Proxy", "netsh winhttp reset proxy"),
        ('-show', 'proxy'): ("Show Proxy", "netsh winhttp show proxy"),
        ('-off', 'proxy'): ("Disable Proxy", "netsh winhttp reset proxy"),
    }

    key = tuple(args[:len(args)])
    if key in cmd_map:
        title, command = cmd_map[key]
        run_cmd(title, command)
    else:
        print("❓ Unknown netsh/ipconfig command, love.")

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
    monitor --live                  Monitor real-time bandwidth usage
    save <profile_name> <settings> Save current settings to profile
    load <profile_name>            Load settings from a profile
    stealth                         Run in background with no terminal window
    log <file> <activity>          Log network activity to a file

    Network Commands (alias for netsh/ipconfig):
    nr -f dns                      (flush DNS)
    nr -r dns                      (register DNS)
    nr -d ip                       (release IP address)
    nr -renew ip                   (renew IP address)
    nr -s config                   (show full IP configuration)
    nr -s interfaces               (show basic IP interfaces)
    nr -show firewall              (show current firewall status)
    nr -reset firewall             (reset all firewall settings to default)
    nr -on firewall                (enable all firewall profiles)
    nr -off firewall               (disable all firewall profiles)
    nr -s interfaces netsh         (show all interfaces via netsh)
    nr -s address                  (display IP address assignments)
    nr -reset winsock              (reset Winsock catalog)
    nr -reset tcp                  (reset TCP/IP stack)
    nr -reset proxy                (reset WinHTTP proxy settings)
    nr -show proxy                 (display current WinHTTP proxy settings)
    nr -off proxy                  (disable WinHTTP proxy)

    Examples:
    network ruler --list
    network ruler app --list
    network ruler srv --list
    network ruler --kill explorer.exe
    network ruler --limit fdm.exe 5mb       (not functional yet)
    network ruler background app --limit 1mb (not functional yet)
    network ruler monitor --live
    network ruler save gaming_profile {"limit": "5mb"} (bandwidth control not functional yet)
    network ruler load gaming_profile
    network ruler log activity.log "Network activity logged"
    network ruler stealth

    Network Command Examples:
    nr -f dns                     (flush DNS)
    nr -r dns                     (register DNS)
    nr -d ip                      (release IP)
    nr -renew ip                  (renew IP)
    nr -s config                  (show full IP config)
    nr -s interfaces              (basic interface list)
    nr -show firewall             (firewall status)
    nr -reset firewall            (reset firewall)
    nr -on firewall               (enable firewall)
    nr -off firewall              (disable firewall)
    nr -s interfaces netsh        (netsh interfaces)
    nr -s address                 (IP assignments)
    nr -reset winsock             (reset Winsock)
    nr -reset tcp                 (reset TCP/IP stack)
    nr -reset proxy               (reset proxy)
    nr -show proxy                (show proxy)
    nr -off proxy                 (disable proxy)

    Alias Info:
    If alias "nr" doesn't work,
    put the 'network_ruler.bat' + 'network_ruler.ps1' files in the System PATH.
    Then you can run from anywhere using 'nr' without needing 'cd' into the folder.
    Example: nr --list
    """
    print(help_text)


def main():
    install_path()

    if sys.argv[0] == 'nr':
        sys.argv[0] = 'network ruler'

    args = sys.argv[1:]

    if len(args) >= 3 and args[0] == 'set' and args[1] == '--alias':
        set_alias(args[2], ' '.join(args[3:]))
        return

    args = resolve_alias(args)

    if not args:
        print("Missing command, honey. Use --help ")
        return

    if args[0] == '--help':
        show_help()
    elif args[0] == '--list':
        list_all()
    elif args[0] == '--kill':
        if len(args) >= 2:
            kill_process(args[1])
        else:
            print("Missing target to kill")
    elif args[0] == '--limit':
        if len(args) >= 3:
            mb = int(args[2].lower().replace('mb', '').replace('m', ''))
            throttle_process(args[1], mb)
        else:
            print("Usage: --limit <proc.exe> 5mb")
    elif args[0] == 'app' and args[1] == '--list':
        if len(args) >= 3:
            list_apps(args[2])
        else:
            list_apps()
    elif args[0] == 'srv' and args[1] == '--list':
        list_services()
    elif args[0] == 'background' and args[1] == 'app' and args[2] == '--limit':
        if len(args) >= 4:
            mb = int(args[3].lower().replace('mb', '').replace('m', ''))
            throttle_background_apps(mb)
        else:
            print("Usage: background app --limit 1mb")
    elif args[0] == 'monitor' and args[1] == '--live':
        monitor_bandwidth()
    elif args[0] == 'save':
        if len(args) >= 3:
            save_profile(args[1], args[2])
        else:
            print("Usage: save <profile_name> <settings>")
    elif args[0] == 'load':
        if len(args) >= 2:
            load_profile(args[1])
        else:
            print("Usage: load <profile_name>")
    elif args[0] == 'stealth':
        stealth_mode()
    elif args[0].startswith('-'):
        handle_net_commands(args)
    else:
        print("Unknown command, sweetheart! Use --help for options.")

if __name__ == '__main__':
    main()


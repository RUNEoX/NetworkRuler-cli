# NETWORK RULER 🧠⚡

**NETWORK RULER** is a lightweight command-line tool written in Python designed for advanced, per-process and per-service network control on Windows. This tool allows you to list, kill, throttle, and monitor apps and services in real-time—built for power users, gamers, and system admins who want precise control.

---

## 🚀 Features

- 🔍 **List all active processes and services**
- ❌ **Kill processes or stop services by name or PID**
- 📈 **Live bandwidth monitoring**
- 💾 **Save/load network profiles** *(works but throttling not yet functional)*
- 📓 **Activity logging to custom file**
- 🧩 **Path installation for system-wide aliasing as `nr`**

---

## 📦 Commands

| Command | Description |
|--------|-------------|
| `--list` | List all running processes and services |
| `app --list` | List only running applications |
| `srv --list` | List only running services |
| `--kill <name|pid>` | Kill a process or stop a service |
| `--limit <process.exe> <speed>` | Throttle a specific process (e.g., `5mb`) *(not functional yet)* |
| `background app --limit <speed>` | Throttle background apps (e.g., `1mb`) *(not functional yet)* |
| `monitor --live` | Real-time bandwidth monitor |
| `save <profile_name> <settings>` | Save current settings to a profile *(useful once throttling works)* |
| `load <profile_name>` | Load settings from saved profile |
| `stealth` | Launch in background without a visible terminal |
| `log <file> <activity>` | Append activity log to a custom file |
| `--help` | Show command usage info |

---

## 🛠 Usage Examples

```bash
network ruler --list
network ruler app --list
network ruler srv --list
network ruler --kill explorer.exe
network ruler --limit fdm.exe 5mb
network ruler background app --limit 1mb
network ruler monitor --live
network ruler save gaming_profile {"limit": "5mb"}
network ruler load gaming_profile
network ruler log activity.log "Logged action at night"
network ruler stealth
```

---

## 💡 Alias Setup

If the `nr` alias doesn’t work by default:

1. Place `network_ruler.bat` and `network_ruler.ps1` in a folder.
2. Add that folder to your system `PATH`.
3. You can now run `nr` globally in the terminal from any path.

```bash
nr --list
```

---

## ⚠️ Note

- Throttling features currently do not function fully due to OS-level limitations.
- Profile saving is functional, but bandwidth limits are not enforced yet.
- Run with admin privileges for service control.

---

## 🔐 Admin Rights

Some features (like service control or stealth execution) **require administrator privileges**.

---

## Author

Made by **RUNEoX** , for the power users who want to command their networks like a true ruler.

---

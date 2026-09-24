import os
import time
import signal
import subprocess
from pathlib import Path
from typing import Set, List, Optional, Dict, Any

# System-critical apps and desktop components that must NEVER be killed
IMMUNE_APP_IDS: Set[str] = {
    "qhealth",
    "plasmashell",
    "org.kde.plasmashell",
    "kwin",
    "kwin_wayland",
    "kwin_x11",
    "krunner",
    "org.kde.krunner",
    "kscreenlocker_greet",
    "lockscreen",
    "systemsettings",
    "org.kde.systemsettings",
    "opencode",
    "ai.opencode.desktop",
    "ai.opencode",
    "desktop",
    "desktop / idle",
    "idle",
    "konsole",
    "alacritty",
    "kitty",
    "bash",
    "zsh",
    "fish",
}

IMMUNE_EXEC_NAMES: Set[str] = {
    "systemd",
    "init",
    "kwin_wayland",
    "kwin_x11",
    "plasmashell",
    "krunner",
    "systemsettings",
    "dbus-daemon",
    "dbus-broker",
    "pipewire",
    "wireplumber",
    "xdg-desktop-portal",
    "xdg-desktop-portal-kde",
}

_last_notification_time: Dict[str, float] = {}


GENERIC_TOKENS: Set[str] = {
    "app", "bin", "client", "desktop", "linux", "org", "com", "net", "io",
    "main", "service", "helper", "daemon", "tool", "manager", "electron",
    "gnome", "mozilla", "google", "microsoft", "github", "freedesktop"
}


def is_immune(app_id: str, app_name: str = "", pid: Optional[int] = None) -> bool:
    """Checks whether an app or PID is protected from termination."""
    app_lower = (app_id or "").lower().strip()
    name_lower = (app_name or "").lower().strip()

    if app_lower.endswith(".desktop"):
        app_lower = app_lower[:-8]

    if app_lower in IMMUNE_APP_IDS or name_lower in IMMUNE_APP_IDS:
        return True

    for imm in ("qhealth", "plasmashell", "kwin", "krunner", "opencode", "systemsettings"):
        if imm in app_lower or imm in name_lower:
            return True

    if pid is not None:
        if pid <= 100 or pid == os.getpid() or pid == os.getppid():
            return True
        try:
            # Check process command line
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read().decode("utf-8", errors="ignore").lower()
                for imm in ("qhealth", "opencode", "kwin", "plasmashell", "systemsettings"):
                    if imm in cmdline:
                        return True

            # Check process comm name
            with open(f"/proc/{pid}/comm", "r") as f:
                comm = f.read().strip().lower()
                if comm in IMMUNE_EXEC_NAMES:
                    return True
        except Exception:
            pass

    return False


def is_process_running(pid: int) -> bool:
    """Checks if a process is alive and not a defunct/zombie."""
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("State:"):
                    state = line.split()[1]
                    return state not in ("Z", "X")
        return True
    except (ProcessLookupError, FileNotFoundError, PermissionError, OSError):
        return False


def get_process_tree(root_pid: int) -> List[int]:
    """Finds root_pid and all its child process IDs from /proc."""
    if root_pid <= 100 or is_immune("", "", root_pid):
        return []

    children = {}
    try:
        for entry in os.listdir("/proc"):
            if entry.isdigit():
                p = int(entry)
                try:
                    with open(f"/proc/{p}/stat", "r") as f:
                        fields = f.read().split()
                        ppid = int(fields[3])
                        children.setdefault(ppid, []).append(p)
                except Exception:
                    pass
    except Exception:
        pass

    queue = [root_pid]
    tree = []
    seen = set()
    while queue:
        curr = queue.pop(0)
        if curr in seen:
            continue
        seen.add(curr)
        if not is_immune("", "", curr):
            tree.append(curr)
            for c in children.get(curr, []):
                queue.append(c)
    return tree


def _process_matches(cleaned_id: str, tokens: List[str], comm: str, exec_path: str) -> bool:
    """Decides whether a process (by comm and argv[0]) belongs to cleaned_id."""
    exec_base = os.path.basename(exec_path) if exec_path else ""
    if cleaned_id == comm or cleaned_id == exec_base:
        return True
    # Whole path component only (e.g. /opt/discord/chrome_crashpad_handler),
    # never a raw substring: 'vi' must not match /usr/lib/libvirt/...
    if cleaned_id in exec_path.split("/"):
        return True
    # comm is truncated to 15 chars by the kernel, so allow a prefix match for long tokens
    return any(t == comm or t == exec_base or (len(t) >= 5 and comm.startswith(t)) for t in tokens)


def find_pids_for_app(app_id: str) -> List[int]:
    """Finds all non-immune processes owned by current user matching app_id."""
    cleaned_id = (app_id or "").lower().strip()
    if cleaned_id.endswith(".desktop"):
        cleaned_id = cleaned_id[:-8]

    if not cleaned_id or is_immune(cleaned_id):
        return []

    # Extract non-generic tokens (e.g. 'brave' from 'brave-browser' or 'firefox' from 'org.mozilla.firefox')
    raw_tokens = [t for t in cleaned_id.replace(".", " ").replace("-", " ").replace("_", " ").split()]
    tokens = [t for t in raw_tokens if len(t) >= 4 and t not in GENERIC_TOKENS]
    uid = os.getuid()
    matched_pids = []

    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            p = int(entry)
            try:
                # Cheap ownership check first, before reading cmdline/comm files
                stat = os.stat(f"/proc/{p}")
                if stat.st_uid != uid or is_immune("", "", p):
                    continue

                comm = ""
                try:
                    with open(f"/proc/{p}/comm", "r") as cf:
                        comm = cf.read().strip().lower()
                except Exception:
                    pass

                cmdline = ""
                try:
                    with open(f"/proc/{p}/cmdline", "rb") as cmdf:
                        cmdline = cmdf.read().decode("utf-8", errors="ignore").lower()
                except Exception:
                    pass

                exec_path = cmdline.split("\x00")[0] if cmdline else ""
                matches = _process_matches(cleaned_id, tokens, comm, exec_path)

                if matches and not is_immune(cleaned_id, comm, p):
                    matched_pids.append(p)
            except Exception:
                pass
    except Exception:
        pass

    return matched_pids


def force_close_app(app_id: str, app_name: str = "", pid: Optional[int] = None) -> int:
    """
    Forcefully terminates an application and all its processes.
    Uses SIGTERM first, then SIGKILL if processes remain alive.
    Returns count of terminated processes.
    """
    if is_immune(app_id, app_name, pid):
        return 0

    target_pids = set()

    # 1. If active window PID is given, gather its whole process tree
    if pid and pid > 100 and not is_immune(app_id, app_name, pid):
        tree = get_process_tree(pid)
        target_pids.update(tree)
        target_pids.add(pid)

    # 2. Also find any other running instances of this app
    other_pids = find_pids_for_app(app_id)
    for op in other_pids:
        if not is_immune(app_id, app_name, op):
            target_pids.add(op)
            for cp in get_process_tree(op):
                target_pids.add(cp)

    # Remove any immune processes from target set
    filtered_pids = [p for p in target_pids if not is_immune(app_id, app_name, p)]
    if not filtered_pids:
        return 0

    # Step 1: Send SIGTERM
    for p in filtered_pids:
        try:
            os.kill(p, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    # Step 2: Brief pause for graceful teardown
    time.sleep(0.15)

    # Step 3: Check remaining living processes and SIGKILL
    terminated_count = 0
    for p in filtered_pids:
        if is_process_running(p):
            try:
                os.kill(p, signal.SIGKILL)
                terminated_count += 1
            except (ProcessLookupError, PermissionError):
                pass
        else:
            terminated_count += 1

    return terminated_count


def send_block_notification(app_name: str, limit_mins: int, app_id: str, is_reopen: bool = False):
    """
    Sends desktop notification with rate-limiting (at most once every 10s per app).
    """
    now = time.time()
    last_time = _last_notification_time.get(app_id, 0.0)
    if now - last_time < 10.0:
        return

    _last_notification_time[app_id] = now
    title = "QHealth — App Blocked" if is_reopen else "QHealth — Daily Budget Exceeded"
    if is_reopen:
        msg = f"{app_name} has reached its daily limit ({limit_mins}m) and cannot be opened today."
    else:
        msg = f"{app_name} daily limit ({limit_mins}m) reached. Force closing application."

    try:
        icon_path = str(Path.home() / ".local" / "share" / "icons" / "qhealth.svg")
        subprocess.run([
            "notify-send",
            "-a", "QHealth",
            "-i", icon_path if os.path.exists(icon_path) else "qhealth",
            "-u", "critical",
            title,
            msg
        ], timeout=3)
    except Exception:
        pass

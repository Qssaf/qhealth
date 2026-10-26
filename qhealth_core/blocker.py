import os
import time
import select
import signal
from typing import Set, List, Optional, Dict

from . import notify
from .app_resolver import app_resolver, TERMINAL_EMULATORS
from .paths import IS_WINDOWS

if IS_WINDOWS:
    from . import win32

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
    "spectacle",
    "org.kde.spectacle",
    "opencode",
    "ai.opencode.desktop",
    "ai.opencode",
    "desktop",
    "desktop / idle",
    "idle",
    "konsole",
    "alacritty",
    "kitty",
    "wezterm",
    "gnome-terminal",
    "foot",
    "xterm",
    "tmux",
    "ssh",
    "bash",
    "zsh",
    "fish",
    "sh",
    "polkit-kde-authentication-agent-1",
}

IMMUNE_EXEC_NAMES: Set[str] = {
    "systemd",
    "init",
    "kwin_wayland",
    "kwin_x11",
    "plasmashell",
    "krunner",
    "systemsettings",
    "spectacle",
    "dbus-daemon",
    "dbus-broker",
    "pipewire",
    "wireplumber",
    "xdg-desktop-portal",
    "xdg-desktop-portal-kde",
    "xwayland",
    "journalctl",
    "polkitd",
    "polkit-kde-authentication-agent-1",
    "ssh-agent",
    "gpg-agent",
    "tmux",
}

# Terminal emulator process names as they appear in /proc/<pid>/comm (max 15 chars)
TERMINAL_PROCESS_NAMES: Set[str] = {name[:15] for name in TERMINAL_EMULATORS}

# Windows shell / session processes (and terminals, like konsole above) that must never be closed
IMMUNE_WINDOWS: Set[str] = {
    "explorer", "dwm", "csrss", "winlogon", "wininit", "lsass", "services", "smss", "svchost", "sihost",
    "taskmgr", "conhost", "ctfmon", "fontdrvhost", "runtimebroker", "searchhost", "searchapp",
    "startmenuexperiencehost", "shellexperiencehost", "applicationframehost", "textinputhost", "lockapp",
    "logonui", "securityhealthsystray", "windowsterminal", "openconsole", "cmd", "powershell", "pwsh",
    "python", "pythonw",
}
IMMUNE_APP_IDS |= IMMUNE_WINDOWS
IMMUNE_EXEC_NAMES |= IMMUNE_WINDOWS

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

    for imm in ("qhealth", "plasmashell", "kwin", "krunner", "opencode", "systemsettings", "spectacle", "konsole", "kitty", "alacritty"):
        if imm in app_lower or imm in name_lower:
            return True

    # Terminals are never blockable, whatever id they report (e.g. org.kde.konsole)
    if app_resolver.is_terminal(app_lower) or app_resolver.is_terminal(name_lower):
        return True

    if pid is not None:
        if pid <= 100 or pid == os.getpid() or pid == os.getppid():
            return True
        if IS_WINDOWS:
            exe = win32.process_name(pid)
            return exe in IMMUNE_EXEC_NAMES or "qhealth" in exe
        try:
            # Check process command line
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read().decode("utf-8", errors="ignore").lower()
                for imm in ("qhealth", "opencode", "kwin", "plasmashell", "systemsettings", "spectacle"):
                    if imm in cmdline:
                        return True

            # Check process comm name. A terminal is spared together with everything running
            # in it: the process-tree walk never descends past an immune process.
            with open(f"/proc/{pid}/comm", "r") as f:
                comm = f.read().strip().lower()
                if comm in IMMUNE_EXEC_NAMES or comm in TERMINAL_PROCESS_NAMES:
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
    uid = os.getuid()
    try:
        for entry in os.listdir("/proc"):
            if entry.isdigit():
                p = int(entry)
                try:
                    if os.stat(f"/proc/{p}").st_uid != uid:
                        continue
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


if IS_WINDOWS:
    # Windows has no /proc: the same three helpers, built on a Toolhelp process snapshot

    def is_process_running(pid: int) -> bool:
        return win32.process_alive(pid)

    def get_process_tree(root_pid: int) -> List[int]:
        if root_pid <= 100 or is_immune("", "", root_pid):
            return []
        procs = win32.processes()
        root_name = next((name for p, _, name in procs if p == root_pid), "")
        if not root_name:
            return []
        # Only same-exe children: Windows recycles PIDs, so a stale parent id must not drag in unrelated programs
        children: Dict[int, List[int]] = {}
        for p, parent, name in procs:
            if name == root_name:
                children.setdefault(parent, []).append(p)
        tree, queue, seen = [], [root_pid], set()
        while queue:
            curr = queue.pop(0)
            if curr in seen:
                continue
            seen.add(curr)
            if not is_immune("", "", curr):
                tree.append(curr)
                queue.extend(children.get(curr, []))
        return tree

    def find_pids_for_app(app_id: str) -> List[int]:
        cleaned_id = (app_id or "").lower().strip()
        if cleaned_id.endswith(".exe"):
            cleaned_id = cleaned_id[:-4]
        if not cleaned_id or is_immune(cleaned_id):
            return []
        raw_tokens = cleaned_id.replace(".", " ").replace("-", " ").replace("_", " ").split()
        tokens = {t for t in raw_tokens if len(t) >= 4 and t not in GENERIC_TOKENS}
        return [p for p, _, name in win32.processes()
                if p != os.getpid() and name not in IMMUNE_EXEC_NAMES and (name == cleaned_id or name in tokens)]


def running_gui_apps() -> List[tuple]:
    """(pid, name) of apps with a window open right now. Linux callers use /proc; this is the Windows view."""
    return win32.gui_processes() if IS_WINDOWS else []


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

    return _terminate_pids(filtered_pids)


_PID_GONE = -1


def _open_pidfd(pid: int) -> Optional[int]:
    """A pidfd for pid, _PID_GONE if it already exited, or None if pidfds are unavailable."""
    try:
        return os.pidfd_open(pid)
    except ProcessLookupError:
        return _PID_GONE
    except (AttributeError, OSError):
        return None  # Windows, Python < 3.9 or kernel < 5.3


def _send_signal(pid: int, pidfd: Optional[int], sig: int) -> bool:
    try:
        if pidfd is not None:
            signal.pidfd_send_signal(pidfd, sig)
        else:
            os.kill(pid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _terminate_pids(pids: List[int]) -> int:
    """
    Ask politely (SIGTERM / WM_CLOSE), a short grace period, then force-kill whatever is still
    alive (SIGKILL / TerminateProcess). Returns the count of processes that ended up terminated.

    On Linux signals go through pidfds when available: a pidfd keeps referring to the original
    process, so a PID recycled during the grace period can never receive the SIGKILL.
    """
    if IS_WINDOWS:
        win32.close_windows(set(pids))
        time.sleep(0.15)
        return sum(1 for p in pids if not win32.process_alive(p) or win32.terminate(p))

    targets = [(p, _open_pidfd(p)) for p in pids]
    try:
        # Step 1: Send SIGTERM
        for p, fd in targets:
            if fd != _PID_GONE:
                _send_signal(p, fd, signal.SIGTERM)

        # Step 2: Brief pause for graceful teardown
        time.sleep(0.15)

        # Step 3: Check remaining living processes and SIGKILL
        terminated_count = 0
        for p, fd in targets:
            if fd == _PID_GONE:
                alive = False
            elif fd is not None:
                # A pidfd turns readable once its process has exited
                alive = not select.select([fd], [], [], 0)[0]
            else:
                alive = is_process_running(p)
            if not alive or _send_signal(p, fd, signal.SIGKILL):
                terminated_count += 1
        return terminated_count
    finally:
        for _, fd in targets:
            if fd is not None and fd >= 0:
                os.close(fd)


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
        msg = f"{app_name} has reached its daily limit ({limit_mins}m) and cannot be opened today. You can add 15 minutes from QHealth."
    else:
        msg = f"{app_name} daily limit ({limit_mins}m) reached. Force closing application."

    notify.send(title, msg, critical=True)


def send_focus_block_notification(app_name: str, app_id: str, remaining_mins: int):
    """
    Sends desktop notification when an app is force-closed during an active focus session.
    Rate-limited to at most once every 6 seconds per app.
    """
    now = time.time()
    notif_key = f"focus_{app_id.lower().strip()}"
    last_time = _last_notification_time.get(notif_key, 0.0)
    if now - last_time < 6.0:
        return

    _last_notification_time[notif_key] = now
    title = "QHealth — Focus Session Active"
    msg = f"{app_name} is blocked during your focus session ({remaining_mins}m remaining)."

    notify.send(title, msg, critical=True)


def send_focus_complete_notification(duration_mins: int):
    """Sends desktop notification when a focus session finishes."""
    title = "QHealth — Focus Session Complete! 🎯"
    msg = f"Great work! You finished your {duration_mins}-minute focus session."

    notify.send(title, msg, critical=False)

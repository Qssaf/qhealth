import os
import glob
import time
import json
import struct
import select
import threading
import subprocess
import collections
from typing import Dict, Any, Optional
from .db import record_activity_chunk, record_input_heatmap_chunk, init_db, get_exceeded_app_budgets
from .app_resolver import app_resolver
from .paths import DATA_DIR, IS_WINDOWS
from .blocker import force_close_app, send_block_notification, send_focus_block_notification

EVENT_STRUCT_FMT = "qqHHi"
EVENT_SIZE = struct.calcsize(EVENT_STRUCT_FMT)

EV_KEY = 1
EV_REL = 2
REL_WHEEL = 8
REL_HWHEEL = 6

IDLE_THRESHOLD_SECONDS = 60

INPUT_ACCESS_HELP = (
    "QHealth cannot read keyboard/mouse devices (/dev/input), so no activity is recorded. "
    "Add yourself to the 'input' group: sudo usermod -aG input $USER, then log out and back in."
)
KWIN_CHECK_INTERVAL_TICKS = 12  # aggregator ticks (5s each) between KWin script health checks

# Kept in the user's private data dir, not world-writable /tmp, so another local
# user cannot swap its contents before KWin loads it.
KWIN_SCRIPT_PATH = DATA_DIR / "kwin_focus.js"

MOUSE_BUTTON_MAP = {
    272: "left",
    273: "right",
    274: "middle",
    275: "side1",
    276: "side2",
}

class ActivityTracker:
    def __init__(self):
        self.running = False
        self.paused = False
        
        # Current active window
        self.current_raw_app = ""
        self.current_title = ""
        self.current_class = ""
        self.current_pid = 0
        self.resolved_app_info = app_resolver.resolve("")

        # Blocked apps state
        self.blocked_app_details = {}
        self.blocked_app_ids = set()
        self._blocked_lock = threading.Lock()

        # Focus session state
        self.focus_session = {}
        self.focus_allowed_ids = set()
        self._focus_lock = threading.Lock()

        # Last external app (to display in Live card when QHealth is open)
        self.last_external_app_info = app_resolver.resolve("")
        self.last_external_title = ""
        self.window_lock = threading.Lock()
        
        # Real-time input stats
        self.input_lock = threading.Lock()
        self.last_input_time = time.monotonic()
        self.last_flush_time = time.monotonic()
        self.is_idle = False
        # True when /dev/input devices exist but none can be opened (user not in the 'input' group)
        self.input_access_denied = False
        
        # Current chunk stats (to be flushed to DB)
        self.chunk_keystrokes = 0
        self.chunk_clicks = 0
        self.chunk_scrolls = 0
        self.chunk_key_codes = collections.defaultdict(int)
        self.chunk_mouse_buttons = collections.defaultdict(int)
        
        # Live sliding window metrics (last 10 seconds)
        self.recent_events = collections.deque() # (timestamp, 'key'|'click'|'scroll'), oldest first
        
        # Background worker threads
        self.input_thread = None
        self.kwin_thread = None
        self.aggregator_thread = None
        
        init_db()

    def start(self):
        self.running = True
        self.last_flush_time = time.monotonic()
        self.last_input_time = time.monotonic()
        
        # Input listener + focused-window watcher: evdev & KWin on Linux, Raw Input & Win32 on Windows
        input_loop, window_loop = (self._win_input_loop, self._win_window_loop) if IS_WINDOWS else (self._input_loop, self._kwin_loop)
        self.input_thread = threading.Thread(target=input_loop, daemon=True)
        self.input_thread.start()
        self.kwin_thread = threading.Thread(target=window_loop, daemon=True)
        self.kwin_thread.start()
        
        # Start database aggregator
        self.aggregator_thread = threading.Thread(target=self._aggregator_loop, daemon=True)
        self.aggregator_thread.start()
        
        print("[QHealth] Activity tracking engine started.")

    def stop(self):
        self.running = False
        if getattr(self, "_raw_input", None):
            self._raw_input.stop()
        self._flush_chunk()
        print("[QHealth] Activity tracking engine stopped.")

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        return self.paused

    def update_blocked_apps(self, blocked_dict: Dict[str, Dict[str, Any]]):
        """Updates the internal set of blocked apps for real-time enforcement."""
        with self._blocked_lock:
            self.blocked_app_details = dict(blocked_dict)
            self.blocked_app_ids = {
                k.lower().strip() for k, v in blocked_dict.items()
                if v.get("block_on_exceed", True)
            }

    def is_app_blocked(self, app_id: str, raw_app: str = "", raw_cls: str = "") -> Optional[Dict[str, Any]]:
        """Returns budget info if the app is currently exceeded and blocked, else None."""
        with self._blocked_lock:
            if not self.blocked_app_ids:
                return None

            candidates = {
                (app_id or "").lower().strip(),
                (raw_app or "").lower().strip(),
                (raw_cls or "").lower().strip()
            }
            # Also check stripped extensions
            for c in list(candidates):
                if c.endswith(".desktop"):
                    candidates.add(c[:-8])

            for cand in candidates:
                if not cand:
                    continue
                if cand in self.blocked_app_ids:
                    return self.blocked_app_details.get(cand)
                # Check for prefix or suffix match (e.g. org.mozilla.firefox -> firefox)
                for b_id in self.blocked_app_ids:
                    if cand == b_id or cand.endswith(f".{b_id}") or b_id.endswith(f".{cand}"):
                        return self.blocked_app_details.get(b_id)
        return None

    def update_focus_session(self, session_data: Dict[str, Any]):
        """Updates internal focus session allowlist and timers."""
        with self._focus_lock:
            self.focus_session = dict(session_data)
            allowed = session_data.get("allowed_apps", [])
            self.focus_allowed_ids = {a.lower().strip() for a in allowed if a}

    def is_focus_session_active(self) -> bool:
        with self._focus_lock:
            if not self.focus_session.get("active"):
                return False
            end_time = float(self.focus_session.get("end_time", 0.0))
            return time.time() < end_time

    def is_app_allowed_in_focus(self, app_id: str, raw_app: str = "", raw_cls: str = "") -> bool:
        """Returns True if the app is permitted under active focus session."""
        with self._focus_lock:
            if not self.focus_session.get("active"):
                return True
            if time.time() >= float(self.focus_session.get("end_time", 0.0)):
                return True

            from .blocker import is_immune
            if is_immune(app_id) or is_immune(raw_app) or is_immune(raw_cls):
                return True

            candidates = {
                (app_id or "").lower().strip(),
                (raw_app or "").lower().strip(),
                (raw_cls or "").lower().strip()
            }
            for c in list(candidates):
                if c.endswith(".desktop"):
                    candidates.add(c[:-8])

            for cand in candidates:
                if not cand:
                    continue
                if cand in self.focus_allowed_ids:
                    return True
                for allowed_id in self.focus_allowed_ids:
                    if (cand == allowed_id or
                        cand.endswith(f".{allowed_id}") or
                        allowed_id.endswith(f".{cand}") or
                        cand.startswith(f"{allowed_id}-") or
                        allowed_id.startswith(f"{cand}-") or
                        cand.startswith(f"{allowed_id}_") or
                        allowed_id.startswith(f"{cand}_")):
                        return True

            res = app_resolver.resolve(raw_app, "", raw_cls)
            res_id = res.get("app_id", "").lower().strip()
            if res_id and res_id in self.focus_allowed_ids:
                return True
            for allowed_id in self.focus_allowed_ids:
                if res_id and (res_id == allowed_id or res_id.endswith(f".{allowed_id}") or allowed_id.endswith(f".{res_id}")):
                    return True

            return False

    def get_live_metrics(self) -> Dict[str, Any]:
        now = time.monotonic()
        with self.input_lock:
            while self.recent_events and now - self.recent_events[0][0] > 10:
                self.recent_events.popleft()

            keys_last_10s = sum(1 for e in self.recent_events if e[1] == 'key')
            clicks_last_10s = sum(1 for e in self.recent_events if e[1] == 'click')
            
            live_kpm = int(keys_last_10s * 6)
            live_wpm = int(live_kpm / 5)
            live_cpm = int(clicks_last_10s * 6)
            idle_state = (now - self.last_input_time) > IDLE_THRESHOLD_SECONDS

        with self.window_lock:
            cur_app_id = self.resolved_app_info.get("app_id", "").lower()
            if cur_app_id == "qhealth" and self.last_external_app_info.get("is_active_window", False):
                app_info = dict(self.last_external_app_info)
                active_title = self.last_external_title
            else:
                app_info = dict(self.resolved_app_info)
                active_title = self.current_title

        with self._focus_lock:
            focus_active = (bool(self.focus_session.get("active", False)) and
                            time.time() < float(self.focus_session.get("end_time", 0.0)))
            rem_secs = max(0, int(float(self.focus_session.get("end_time", 0.0)) - time.time())) if focus_active else 0
            focus_dur = self.focus_session.get("duration_minutes", 0)
            focus_allowed = sorted(list(self.focus_allowed_ids))

        return {
            "active_app": app_info.get("display_name", "Desktop / Idle"),
            "app_id": app_info.get("app_id", ""),
            "app_icon": app_info.get("icon", ""),
            "category": app_info.get("category", "System"),
            "is_active_window": app_info.get("is_active_window", False),
            "active_title": active_title,
            "live_wpm": live_wpm,
            "live_cpm": live_cpm,
            "is_idle": idle_state,
            "is_paused": self.paused,
            "seconds_since_input": int(now - self.last_input_time),
            "input_access_denied": self.input_access_denied,
            "focus_active": focus_active,
            "focus_remaining_seconds": rem_secs,
            "focus_duration_minutes": focus_dur,
            "focus_allowed_apps": focus_allowed
        }

    def _input_loop(self):
        """Monitors all /dev/input/event* devices asynchronously."""
        opened_fds = {}
        
        def refresh_devices():
            self._refresh_input_devices(opened_fds)

        refresh_devices()
        last_refresh = time.time()

        while self.running:
            now = time.time()
            if now - last_refresh > 5.0:
                refresh_devices()
                last_refresh = now

            if not opened_fds:
                time.sleep(1.0)
                continue

            rlist = list(opened_fds.values())
            try:
                # Sleep in the kernel until input arrives; wake at most every 5 s for hot-plug rescans
                readable, _, _ = select.select(rlist, [], [], 5.0)
            except Exception:
                time.sleep(0.1)
                continue

            for fd in readable:
                try:
                    data = os.read(fd, EVENT_SIZE * 64)
                    if not data or self.paused:
                        continue

                    usable = len(data) - len(data) % EVENT_SIZE
                    cur_time = time.monotonic()
                    # One lock acquisition per read() batch instead of one per event
                    with self.input_lock:
                        for _sec, _usec, ev_type, ev_code, ev_val in struct.iter_unpack(EVENT_STRUCT_FMT, data[:usable]):
                            if ev_type == EV_KEY:
                                if ev_val in (1, 2): # Key down or key repeat
                                    self.last_input_time = cur_time
                                if ev_val == 1: # Single discrete press
                                    if ev_code >= 0x110 and ev_code <= 0x117: # Mouse button
                                        btn_name = MOUSE_BUTTON_MAP.get(ev_code, "other")
                                        self.chunk_mouse_buttons[btn_name] += 1
                                        self.chunk_clicks += 1
                                        self.recent_events.append((cur_time, 'click'))
                                    elif ev_code < 0x100: # Physical keyboard key (< 256)
                                        self.chunk_key_codes[ev_code] += 1
                                        self.chunk_keystrokes += 1
                                        self.recent_events.append((cur_time, 'key'))
                            elif ev_type == EV_REL and (ev_code == REL_WHEEL or ev_code == REL_HWHEEL):
                                self.last_input_time = cur_time
                                self.chunk_scrolls += 1
                                self.recent_events.append((cur_time, 'scroll'))
                except OSError:
                    # Clean up disconnected / invalid FDs
                    try:
                        os.close(fd)
                    except:
                        pass
                    for p, f in list(opened_fds.items()):
                        if f == fd:
                            del opened_fds[p]
                except Exception:
                    pass

        for fd in opened_fds.values():
            try:
                os.close(fd)
            except:
                pass

    def _refresh_input_devices(self, opened_fds: Dict[str, int]):
        """Opens newly attached /dev/input/event* devices and closes vanished ones."""
        current_paths = set(glob.glob("/dev/input/event*"))
        for path in list(opened_fds.keys()):
            if path not in current_paths:
                try:
                    os.close(opened_fds[path])
                except:
                    pass
                del opened_fds[path]
        denied = 0
        for path in current_paths:
            if path not in opened_fds:
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                    opened_fds[path] = fd
                except PermissionError:
                    denied += 1
                except Exception:
                    pass
        # Without access every minute looks idle and nothing is recorded, so say why
        self.input_access_denied = not opened_fds and denied > 0

    def _win_input_loop(self):
        """Windows: physical keyboard / mouse events via Raw Input (same counters as the evdev loop)."""
        from .win32 import RawInputListener

        def on_key(code, repeat):
            if self.paused:
                return
            now = time.monotonic()
            with self.input_lock:
                self.last_input_time = now
                if not repeat and code is not None:
                    self.chunk_key_codes[code] += 1
                    self.chunk_keystrokes += 1
                    self.recent_events.append((now, 'key'))

        def on_click(button):
            if self.paused:
                return
            now = time.monotonic()
            with self.input_lock:
                self.last_input_time = now
                self.chunk_mouse_buttons[button] += 1
                self.chunk_clicks += 1
                self.recent_events.append((now, 'click'))

        def on_scroll():
            if self.paused:
                return
            now = time.monotonic()
            with self.input_lock:
                self.last_input_time = now
                self.chunk_scrolls += 1
                self.recent_events.append((now, 'scroll'))

        self._raw_input = RawInputListener(on_key, on_click, on_scroll)
        self._raw_input.run()

    def _win_window_loop(self):
        """Windows: poll the foreground window once a second (title changes included, e.g. browser tabs)."""
        from . import win32
        last = None
        while self.running:
            try:
                fg = win32.foreground_window()
                if fg != last:
                    last = fg
                    if fg is None:
                        self._handle_focus("", "", "", 0)
                    else:
                        pid, title, cls = fg
                        path = win32.process_path(pid)
                        app_id = "qhealth" if pid == os.getpid() else win32.exe_stem(path)
                        if app_id != "qhealth" and path and not app_resolver.is_known(app_id):
                            app_resolver.register_app(app_id, win32.file_description(path), path)
                        self._handle_focus(app_id, title, cls, pid)
            except Exception:
                pass
            time.sleep(1.0)

    def _inject_kwin_script(self) -> bool:
        """Injects or reloads the active focus monitor in KWin."""
        kwin_script = """
        var activeWin = null;
        function report() {
            var win = workspace.activeWindow;
            if (win && !win.minimized && !win.popupWindow && !win.specialWindow) {
                var app = win.desktopFileName || win.resourceClass || win.resourceName || "";
                var title = win.caption || "";
                var cls = win.resourceClass || win.resourceName || "";
                var pid = win.pid || 0;
                console.log("QHEALTH_FOCUS:" + JSON.stringify({
                    app: app,
                    title: title,
                    cls: cls,
                    pid: pid
                }));
            } else {
                console.log("QHEALTH_FOCUS:" + JSON.stringify({
                    app: "",
                    title: "",
                    cls: "",
                    pid: 0
                }));
            }
        }
        function hookActive() {
            if (activeWin) {
                try { activeWin.captionChanged.disconnect(report); } catch(e) {}
            }
            activeWin = workspace.activeWindow;
            if (activeWin) {
                try { activeWin.captionChanged.connect(report); } catch(e) {}
            }
            report();
        }
        if (workspace.windowActivated) {
            workspace.windowActivated.connect(hookActive);
        }
        if (workspace.activeWindowChanged) {
            workspace.activeWindowChanged.connect(hookActive);
        }
        if (workspace.windowRemoved) {
            workspace.windowRemoved.connect(report);
        }
        hookActive();
        """
        script_path = str(KWIN_SCRIPT_PATH)
        try:
            KWIN_SCRIPT_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with open(script_path, "w") as f:
                f.write(kwin_script)

            # Unload any previously loaded script (including legacy paths) to prevent duplicate signal handlers
            legacy = (f"/tmp/qhealth_kwin_{os.getuid()}.js", str(DATA_DIR / f"kwin_script_{os.getuid()}.js"))
            for old_path in (script_path,) + legacy:
                subprocess.run([
                    "busctl", "--user", "call", "org.kde.KWin", "/Scripting",
                    "org.kde.kwin.Scripting", "unloadScript", "s", old_path
                ], capture_output=True, timeout=3)

            res_load = subprocess.run([
                "busctl", "--user", "call", "org.kde.KWin", "/Scripting",
                "org.kde.kwin.Scripting", "loadScript", "s", script_path
            ], capture_output=True, timeout=5)
            
            if res_load.returncode == 0:
                subprocess.run([
                    "busctl", "--user", "call", "org.kde.KWin", "/Scripting",
                    "org.kde.kwin.Scripting", "start"
                ], capture_output=True, timeout=5)
                return True
        except Exception:
            pass
        return False

    def _ensure_kwin_script(self):
        """Re-injects the focus script if KWin restarted, since a restart drops loaded scripts."""
        try:
            res = subprocess.run([
                "busctl", "--user", "call", "org.kde.KWin", "/Scripting",
                "org.kde.kwin.Scripting", "isScriptLoaded", "s", str(KWIN_SCRIPT_PATH)
            ], capture_output=True, text=True, timeout=3)
        except Exception:
            return
        # Only act on a definite "not loaded" answer; no KWin on the bus means nothing to fix
        if res.returncode == 0 and res.stdout.strip() == "b false":
            self._inject_kwin_script()

    def _kwin_loop(self):
        """Integrates with KDE Plasma 6 KWin via Scripting and journalctl with auto-boot retry."""
        while self.running:
            proc = None
            try:
                # Follow the journal from just before (re)injecting: the script reports the already-focused
                # window the moment it loads, and that line used to be missed until the next focus change.
                since = f"@{int(time.time()) - 1}"
                proc = subprocess.Popen(
                    ["journalctl", "--user", "-u", "plasma-kwin_wayland.service", "-u", "plasma-kwin_x11.service",
                     "-f", "--since", since, "-o", "cat"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                # Retry injection until KWin is ready on DBus (handles cold PC boot)
                while self.running and not self._inject_kwin_script():
                    time.sleep(2.0)

                for line in iter(proc.stdout.readline, ''):
                    if not self.running:
                        break
                    if "QHEALTH_FOCUS:" in line or "CHRONOS_FOCUS:" in line:
                        prefix = "QHEALTH_FOCUS:" if "QHEALTH_FOCUS:" in line else "CHRONOS_FOCUS:"
                        try:
                            json_str = line.split(prefix, 1)[1].strip()
                            data = json.loads(json_str)
                            raw_app = data.get("app", "")
                            raw_title = data.get("title", "")
                            raw_cls = data.get("cls", "")
                            pid = int(data.get("pid", 0) or 0)
                            
                            self._handle_focus(raw_app, raw_title, raw_cls, pid)
                        except Exception:
                            pass
            except Exception:
                time.sleep(2.0)
            finally:
                if proc:
                    try:
                        proc.terminate()
                        proc.wait(timeout=1.0)
                    except Exception:
                        pass
                if self.running:
                    time.sleep(2.0)

    def _handle_focus(self, raw_app: str, raw_title: str, raw_cls: str, pid: int):
        """A window gained focus (or its title changed): enforce focus sessions / budgets, then track it."""
        resolved = app_resolver.resolve(raw_app, raw_title, raw_cls)
        is_qhealth = (
            "qhealth" in raw_app.lower() or
            "qhealth" in raw_cls.lower() or
            resolved.get("app_id") == "qhealth"
        )

        # Check Focus Session enforcement
        if self.is_focus_session_active() and not is_qhealth:
            target_id = resolved.get("app_id", raw_app)
            app_name = resolved.get("display_name", raw_app or "Application")
            if not self.is_app_allowed_in_focus(target_id, raw_app, raw_cls):
                with self._focus_lock:
                    rem_secs = max(0, int(float(self.focus_session.get("end_time", 0.0)) - time.time()))
                rem_mins = max(1, (rem_secs + 59) // 60)
                force_close_app(target_id, app_name, pid)
                send_focus_block_notification(app_name, target_id, rem_mins)

                with self.window_lock:
                    self.current_raw_app = ""
                    self.current_title = ""
                    self.current_class = ""
                    self.current_pid = 0
                    self.resolved_app_info = app_resolver.resolve("")
                return

        # Check if the focused app is exceeded and blocked
        blocked_info = self.is_app_blocked(resolved.get("app_id", ""), raw_app, raw_cls)
        if blocked_info and not is_qhealth:
            # The blocked set refreshes every 5s; re-read it so a "+15 min"
            # granted a moment ago lets the app open instead of killing it
            try:
                self.update_blocked_apps(get_exceeded_app_budgets())
                blocked_info = self.is_app_blocked(resolved.get("app_id", ""), raw_app, raw_cls)
            except Exception:
                pass
        if blocked_info and not is_qhealth:
            target_id = resolved.get("app_id", raw_app)
            app_name = resolved.get("display_name", raw_app or "Application")
            limit_mins = blocked_info.get("effective_limit_minutes", blocked_info.get("daily_limit_minutes", 0))
            force_close_app(target_id, app_name, pid)
            send_block_notification(app_name, limit_mins, target_id, is_reopen=True)

            with self.window_lock:
                self.current_raw_app = ""
                self.current_title = ""
                self.current_class = ""
                self.current_pid = 0
                self.resolved_app_info = app_resolver.resolve("")
            return

        with self.window_lock:
            self.current_raw_app = raw_app
            self.current_title = raw_title
            self.current_class = raw_cls
            self.current_pid = pid
            self.resolved_app_info = resolved
            if not is_qhealth and resolved.get("is_active_window", False):
                self.last_external_app_info = resolved
                self.last_external_title = raw_title

    def _flush_chunk(self):
        now = time.monotonic()
        with self.input_lock:
            keys = self.chunk_keystrokes
            clicks = self.chunk_clicks
            scrolls = self.chunk_scrolls
            key_codes = dict(self.chunk_key_codes)
            mouse_btns = dict(self.chunk_mouse_buttons)

            self.chunk_keystrokes = 0
            self.chunk_clicks = 0
            self.chunk_scrolls = 0
            self.chunk_key_codes.clear()
            self.chunk_mouse_buttons.clear()

            # Prevent unbounded recent_events growth over long 24/7 runs
            while self.recent_events and now - self.recent_events[0][0] > 12:
                self.recent_events.popleft()

        with self.window_lock:
            app_info = dict(self.resolved_app_info)
            title = self.current_title

        is_afk = (now - self.last_input_time) > IDLE_THRESHOLD_SECONDS
        
        # Calculate exact elapsed duration, capped at 15s to prevent system suspend/wake jumps
        raw_elapsed = int(round(now - self.last_flush_time))
        self.last_flush_time = now
        elapsed = min(max(0, raw_elapsed), 15)
        
        is_active = app_info.get("is_active_window", False)
        duration = elapsed if (is_active and not is_afk and not self.paused) else 0
        
        try:
            if duration > 0 or keys > 0 or clicks > 0 or scrolls > 0:
                record_activity_chunk(
                    app_id=app_info.get("app_id", "unknown"),
                    app_name=app_info.get("display_name", "Unknown App"),
                    window_title=title,
                    duration_seconds=duration,
                    keystrokes=keys,
                    clicks=clicks,
                    scrolls=scrolls,
                    category=app_info.get("category")
                )

            if key_codes or mouse_btns:
                record_input_heatmap_chunk(key_codes, mouse_btns)
        except Exception:
            pass

    def _aggregator_loop(self):
        ticks = 0
        while self.running:
            time.sleep(5.0)
            ticks += 1
            if not IS_WINDOWS and ticks % KWIN_CHECK_INTERVAL_TICKS == 0:
                self._ensure_kwin_script()
            if not self.paused:
                self._flush_chunk()
            else:
                # Don't credit paused time to the first chunk after resuming
                self.last_flush_time = time.monotonic()

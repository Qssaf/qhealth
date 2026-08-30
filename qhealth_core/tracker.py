import os
import sys
import glob
import time
import json
import struct
import select
import threading
import subprocess
import collections
from pathlib import Path
from typing import Dict, Any, Optional
from .db import record_activity_chunk, record_input_heatmap_chunk, init_db
from .app_resolver import app_resolver

EVENT_STRUCT_FMT = "qqHHi"
EVENT_SIZE = struct.calcsize(EVENT_STRUCT_FMT)

EV_KEY = 1
EV_REL = 2
REL_WHEEL = 8
REL_HWHEEL = 6

IDLE_THRESHOLD_SECONDS = 60

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
        self.resolved_app_info = app_resolver.resolve("")
        self.window_lock = threading.Lock()
        
        # Real-time input stats
        self.input_lock = threading.Lock()
        self.last_input_time = time.time()
        self.last_flush_time = time.time()
        self.is_idle = False
        
        # Current chunk stats (to be flushed to DB)
        self.chunk_keystrokes = 0
        self.chunk_clicks = 0
        self.chunk_scrolls = 0
        self.chunk_key_codes = collections.defaultdict(int)
        self.chunk_mouse_buttons = collections.defaultdict(int)
        
        # Live sliding window metrics (last 10 seconds)
        self.recent_events = [] # list of (timestamp, 'key'|'click')
        
        # Background worker threads
        self.input_thread = None
        self.kwin_thread = None
        self.aggregator_thread = None
        
        init_db()

    def start(self):
        self.running = True
        self.last_flush_time = time.time()
        self.last_input_time = time.time()
        
        # Start input listener
        self.input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self.input_thread.start()
        
        # Start KWin window listener
        self.kwin_thread = threading.Thread(target=self._kwin_loop, daemon=True)
        self.kwin_thread.start()
        
        # Start database aggregator
        self.aggregator_thread = threading.Thread(target=self._aggregator_loop, daemon=True)
        self.aggregator_thread.start()
        
        print("[QHealth] Activity tracking engine started.")

    def stop(self):
        self.running = False
        self._flush_chunk()
        print("[QHealth] Activity tracking engine stopped.")

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        return self.paused

    def get_live_metrics(self) -> Dict[str, Any]:
        now = time.time()
        with self.input_lock:
            self.recent_events = [e for e in self.recent_events if now - e[0] <= 10]
            
            keys_last_10s = sum(1 for e in self.recent_events if e[1] == 'key')
            clicks_last_10s = sum(1 for e in self.recent_events if e[1] == 'click')
            
            live_kpm = int(keys_last_10s * 6)
            live_wpm = int(live_kpm / 5)
            live_cpm = int(clicks_last_10s * 6)
            idle_state = (now - self.last_input_time) > IDLE_THRESHOLD_SECONDS

        with self.window_lock:
            app_info = dict(self.resolved_app_info)
            active_title = self.current_title

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
            "seconds_since_input": int(now - self.last_input_time)
        }

    def _input_loop(self):
        """Monitors all /dev/input/event* devices asynchronously."""
        opened_fds = {}
        
        def refresh_devices():
            nonlocal opened_fds
            current_paths = set(glob.glob("/dev/input/event*"))
            for path in list(opened_fds.keys()):
                if path not in current_paths:
                    try:
                        os.close(opened_fds[path])
                    except:
                        pass
                    del opened_fds[path]
            for path in current_paths:
                if path not in opened_fds:
                    try:
                        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                        opened_fds[path] = fd
                    except Exception:
                        pass

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
                readable, _, _ = select.select(rlist, [], [], 0.5)
            except Exception:
                time.sleep(0.1)
                continue

            for fd in readable:
                try:
                    data = os.read(fd, EVENT_SIZE * 32)
                    if not data:
                        continue
                    
                    event_count = len(data) // EVENT_SIZE
                    for i in range(event_count):
                        chunk = data[i * EVENT_SIZE : (i + 1) * EVENT_SIZE]
                        sec, usec, ev_type, ev_code, ev_val = struct.unpack(EVENT_STRUCT_FMT, chunk)
                        
                        if self.paused:
                            continue

                        cur_time = time.time()
                        if ev_type == EV_KEY:
                            if ev_val in (1, 2): # Key down or key repeat
                                with self.input_lock:
                                    self.last_input_time = cur_time
                            if ev_val == 1: # Single discrete press
                                with self.input_lock:
                                    if ev_code >= 0x110 and ev_code <= 0x117: # Mouse button
                                        btn_name = MOUSE_BUTTON_MAP.get(ev_code, "other")
                                        self.chunk_mouse_buttons[btn_name] += 1
                                        self.chunk_clicks += 1
                                        self.recent_events.append((cur_time, 'click'))
                                    else: # Keyboard key
                                        self.chunk_key_codes[ev_code] += 1
                                        self.chunk_keystrokes += 1
                                        self.recent_events.append((cur_time, 'key'))
                        elif ev_type == EV_REL and (ev_code == REL_WHEEL or ev_code == REL_HWHEEL):
                            with self.input_lock:
                                self.last_input_time = cur_time
                                self.chunk_scrolls += 1
                                self.recent_events.append((cur_time, 'click'))
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

    def _kwin_loop(self):
        """Integrates with KDE Plasma 6 KWin via Scripting and journalctl."""
        kwin_script = """
        function report() {
            var win = workspace.activeWindow;
            if (win && !win.minimized && !win.hidden && win.normalWindow) {
                var app = win.desktopFileName || win.resourceClass || win.resourceName || "";
                console.log("QHEALTH_FOCUS:" + JSON.stringify({
                    app: app,
                    title: win.caption || "",
                    cls: win.resourceClass || ""
                }));
            } else {
                console.log("QHEALTH_FOCUS:" + JSON.stringify({
                    app: "",
                    title: "",
                    cls: ""
                }));
            }
        }
        workspace.windowActivated.connect(report);
        workspace.windowRemoved.connect(report);
        report();
        """
        script_path = "/tmp/qhealth_kwin.js"
        try:
            with open(script_path, "w") as f:
                f.write(kwin_script)
            
            subprocess.run([
                "busctl", "--user", "call", "org.kde.KWin", "/Scripting",
                "org.kde.kwin.Scripting", "loadScript", "s", script_path
            ], capture_output=True, timeout=5)
            
            subprocess.run([
                "busctl", "--user", "call", "org.kde.KWin", "/Scripting",
                "org.kde.kwin.Scripting", "start"
            ], capture_output=True, timeout=5)
        except Exception as e:
            print("[QHealth] Warning: Could not inject KWin script directly:", e)

        while self.running:
            try:
                proc = subprocess.Popen(
                    ["journalctl", "--user", "-u", "plasma-kwin_wayland.service", "-f", "-n", "0", "-o", "cat"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                for line in iter(proc.stdout.readline, ''):
                    if not self.running:
                        proc.terminate()
                        break
                    if "QHEALTH_FOCUS:" in line or "CHRONOS_FOCUS:" in line:
                        prefix = "QHEALTH_FOCUS:" if "QHEALTH_FOCUS:" in line else "CHRONOS_FOCUS:"
                        try:
                            json_str = line.split(prefix, 1)[1].strip()
                            data = json.loads(json_str)
                            raw_app = data.get("app", "")
                            raw_title = data.get("title", "")
                            raw_cls = data.get("cls", "")
                            
                            resolved = app_resolver.resolve(raw_app, raw_title, raw_cls)
                            
                            with self.window_lock:
                                self.current_raw_app = raw_app
                                self.current_title = raw_title
                                self.current_class = raw_cls
                                self.resolved_app_info = resolved
                        except Exception:
                            pass
            except Exception as e:
                time.sleep(2.0)

    def _flush_chunk(self):
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

        with self.window_lock:
            app_info = dict(self.resolved_app_info)
            title = self.current_title

        now = time.time()
        is_afk = (now - self.last_input_time) > IDLE_THRESHOLD_SECONDS
        
        # Calculate exact elapsed duration instead of hardcoded 5s
        elapsed = int(round(now - self.last_flush_time))
        self.last_flush_time = now
        
        is_active = app_info.get("is_active_window", False)
        duration = elapsed if (is_active and not is_afk and not self.paused) else 0
        
        try:
            if duration > 0 or keys > 0 or clicks > 0:
                record_activity_chunk(
                    app_id=app_info.get("app_id", "unknown"),
                    app_name=app_info.get("display_name", "Unknown App"),
                    window_title=title,
                    duration_seconds=duration,
                    keystrokes=keys,
                    clicks=clicks,
                    scrolls=scrolls
                )

            if key_codes or mouse_btns:
                record_input_heatmap_chunk(key_codes, mouse_btns)
        except Exception as e:
            pass

    def _aggregator_loop(self):
        while self.running:
            time.sleep(5.0)
            if not self.paused:
                self._flush_chunk()

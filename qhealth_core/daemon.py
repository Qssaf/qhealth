import os
import json
import time
import signal
import sys
import datetime
import threading
from typing import Optional
from .tracker import ActivityTracker
from .db import (
    init_db, is_paused_setting, get_stats_by_range,
    get_all_app_budgets, get_exceeded_app_budgets, vacuum_and_cleanup_db,
    get_focus_session, stop_focus_session
)
from .blocker import (
    force_close_app, send_block_notification,
    send_focus_block_notification, send_focus_complete_notification
)
from .app_resolver import app_resolver
from . import notify
from .paths import DATA_DIR, STATE_FILE, PID_FILE

STATE_DIR = DATA_DIR

class QHealthDaemon:
    def __init__(self):
        self.running = False
        self.notified_budget_alerts = set()
        self._lock_file = None
        self._was_focus_active = False
        self._last_focus_dur_mins = 60
        self._stopped = False
        init_db()
        self.tracker = ActivityTracker()

    def start(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        
        try:
            import fcntl
            self._lock_file = open(PID_FILE, "a+")
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_file.seek(0)
            self._lock_file.truncate()
            self._lock_file.write(str(os.getpid()))
            self._lock_file.flush()
        except (IOError, BlockingIOError):
            print(f"[QHealth Daemon] Another daemon instance is already active. Exiting.")
            sys.exit(0)

        self.running = True
        self.tracker.start()

        # Handle clean shutdown signals
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        print(f"[QHealth Daemon] Running 24/7 background tracking (PID: {os.getpid()})...")
        self._run()

    def start_embedded(self):
        """Windows: tracking lives inside the tray app, because a service can't see the user's desktop.
        Single-instance is the tray app's job, so no PID lock or signal handlers here."""
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.running = True
        self.tracker.start()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        loop_count = 0
        today_dur = 0
        today_stats = {}
        last_state = None
        try:
            while self.running:
                # Sync paused state with DB setting
                self.tracker.paused = is_paused_setting()

                # Sync Focus Session state every second
                focus_session = get_focus_session()
                self.tracker.update_focus_session(focus_session)
                focus_active = focus_session.get("active", False)

                if self._was_focus_active and not focus_active:
                    self._was_focus_active = False
                    send_focus_complete_notification(self._last_focus_dur_mins)
                elif focus_active:
                    self._was_focus_active = True
                    self._last_focus_dur_mins = focus_session.get("duration_minutes", 60)

                    # Enforce focus restriction on active window
                    cur_pid = None
                    with self.tracker.window_lock:
                        cur_app_id = self.tracker.resolved_app_info.get("app_id", "").lower()
                        cur_raw = self.tracker.current_raw_app
                        cur_cls = self.tracker.current_class
                        cur_pid = getattr(self.tracker, "current_pid", None)
                        cur_name = self.tracker.resolved_app_info.get("display_name", cur_raw or "Application")

                    if (cur_app_id and cur_app_id != "qhealth" and
                        not self.tracker.is_app_allowed_in_focus(cur_app_id, cur_raw, cur_cls)):
                        rem_secs = focus_session.get("remaining_seconds", 0)
                        rem_mins = max(1, (rem_secs + 59) // 60)
                        force_close_app(cur_app_id, cur_name, cur_pid)
                        send_focus_block_notification(cur_name, cur_app_id, rem_mins)
                        with self.tracker.window_lock:
                            self.tracker.current_raw_app = ""
                            self.tracker.current_title = ""
                            self.tracker.current_class = ""
                            self.tracker.current_pid = 0
                            self.tracker.resolved_app_info = app_resolver.resolve("")

                # Refresh today duration and budget alerts every 5 iterations
                if loop_count % 5 == 0:
                    try:
                        today_stats = get_stats_by_range("day")
                        today_dur = today_stats.get("total_duration", 0)
                        exceeded = get_exceeded_app_budgets()
                        self.tracker.update_blocked_apps(exceeded)
                        self._check_budget_limits(today_stats, exceeded)
                    except Exception:
                        pass

                if loop_count % 3600 == 0 and loop_count > 0:
                    try:
                        vacuum_and_cleanup_db()
                    except Exception:
                        pass

                # Update live state file for GUI & Plasma widget every 1 second
                metrics = self.tracker.get_live_metrics()
                metrics["today_duration_seconds"] = today_dur
                hrs = today_dur // 3600
                mins = (today_dur % 3600) // 60
                metrics["today_duration_formatted"] = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"

                # Add quick summary for tray / widgets
                top_app = today_stats.get("apps", [{}])[0] if today_stats.get("apps") else {}
                metrics["top_app_name"] = top_app.get("app_name", "")
                metrics["top_app_percentage"] = top_app.get("percentage", 0)
                metrics["today_keystrokes"] = today_stats.get("total_keystrokes", 0)
                metrics["today_clicks"] = today_stats.get("total_clicks", 0)

                # Only rewrite the file when something a reader shows has changed
                # (seconds_since_input ticks every second and would force a write each loop)
                state = json.dumps({k: v for k, v in metrics.items() if k != "seconds_since_input"}, sort_keys=True)
                if state != last_state or not STATE_FILE.exists():
                    temp_file = STATE_DIR / "live_state.tmp"
                    try:
                        with open(temp_file, "w") as f:
                            json.dump(metrics, f)
                        temp_file.replace(STATE_FILE)
                        last_state = state
                    except Exception:
                        pass

                loop_count += 1
                time.sleep(1.0)
        finally:
            self.stop()

    def _check_budget_limits(self, stats: dict, exceeded: Optional[dict] = None):
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        if self.notified_budget_alerts:
            self.notified_budget_alerts = {k for k in self.notified_budget_alerts if k.startswith(today_str)}
        budgets = get_all_app_budgets()
        if exceeded is None:
            exceeded = get_exceeded_app_budgets()

        for app in stats.get("apps", []):
            a_id = app.get("app_id", "").lower()
            b_info = budgets.get(a_id)
            if not b_info or not b_info.get("enabled", 1) or b_info.get("daily_limit_minutes", 0) <= 0:
                continue
            limit_mins = b_info["daily_limit_minutes"]
            dur_secs = app.get("duration", 0)
            dur_mins = dur_secs / 60.0
            app_name = app.get("app_name", a_id)

            # 80% Threshold
            if dur_mins >= limit_mins * 0.8 and f"{today_str}_{a_id}_80" not in self.notified_budget_alerts:
                self.notified_budget_alerts.add(f"{today_str}_{a_id}_80")
                self._send_notification(
                    f"QHealth — 80% Limit Warning",
                    f"You have used {app_name} for {int(dur_mins)}m (Daily budget: {limit_mins}m)."
                )

            # 100% Threshold
            if dur_mins >= limit_mins and f"{today_str}_{a_id}_100" not in self.notified_budget_alerts:
                self.notified_budget_alerts.add(f"{today_str}_{a_id}_100")
                block_on_exceed = bool(b_info.get("block_on_exceed", 1))
                if block_on_exceed:
                    send_block_notification(app_name, limit_mins, a_id, is_reopen=False)
                else:
                    self._send_notification(
                        f"QHealth — Daily Budget Exceeded",
                        f"{app_name} limit reached ({int(dur_mins)}m / {limit_mins}m)!"
                    )

            # Enforcement: If exceeded and block enabled, ensure app processes are terminated
            if a_id in exceeded and b_info.get("block_on_exceed", 1):
                cur_pid = None
                with self.tracker.window_lock:
                    cur_app_id = self.tracker.resolved_app_info.get("app_id", "").lower()
                    cur_raw = self.tracker.current_raw_app.lower()
                    if cur_app_id == a_id or cur_raw == a_id or a_id.endswith(cur_raw) or cur_raw.endswith(a_id):
                        cur_pid = getattr(self.tracker, "current_pid", None)
                        self.tracker.current_raw_app = ""
                        self.tracker.current_title = ""
                        self.tracker.current_pid = 0
                force_close_app(a_id, app_name, cur_pid)

    def _send_notification(self, title: str, message: str):
        notify.send(title, message)

    def _handle_signal(self, signum, frame):
        self.running = False

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        self.running = False
        self.tracker.stop()
        if self._lock_file:
            try:
                self._lock_file.close()
            except Exception:
                pass
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)
        if STATE_FILE.exists():
            STATE_FILE.unlink(missing_ok=True)
        print("[QHealth Daemon] Stopped cleanly.")

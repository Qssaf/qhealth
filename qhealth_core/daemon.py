import os
import json
import time
import signal
import sys
import threading
from .tracker import ActivityTracker, INPUT_ACCESS_HELP
from .db import (
    init_db, is_paused_setting, get_stats_by_range, vacuum_and_cleanup_db, get_break_reminder_minutes,
    get_focus_session
)
from .blocker import force_close_app, send_focus_block_notification, send_focus_complete_notification
from .wellbeing import BudgetEnforcer, BreakReminder, send_notification
from .app_resolver import app_resolver
from .paths import DATA_DIR, STATE_FILE, PID_FILE

STATE_DIR = DATA_DIR

class QHealthDaemon:
    def __init__(self):
        self.running = False
        self._lock_file = None
        self._warned_input_access = False
        self._was_focus_active = False
        self._last_focus_dur_mins = 60
        self._stopped = False
        init_db()
        self.tracker = ActivityTracker()
        self.budget_enforcer = BudgetEnforcer(self.tracker)
        self.break_reminder = BreakReminder(self.tracker)

    def start(self):
        """Standalone daemon (Linux systemd service): single-instance lock, signals, loop on this thread."""
        STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

        try:
            import fcntl
            self._lock_file = open(PID_FILE, "a+")
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_file.seek(0)
            self._lock_file.truncate()
            self._lock_file.write(str(os.getpid()))
            self._lock_file.flush()
        except (IOError, BlockingIOError):
            print("[QHealth Daemon] Another daemon instance is already active. Exiting.")
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
        STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.running = True
        self.tracker.start()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        loop_count = 0
        today_dur = 0
        today_stats = {}
        last_state, last_write = None, 0.0
        try:
            while self.running:
                # Sync paused state with DB setting
                self.tracker.paused = is_paused_setting()

                # Sync Focus Session state every second
                self._sync_focus_session()

                # Refresh today duration and budget alerts every 5 iterations
                if loop_count % 5 == 0:
                    try:
                        today_stats = get_stats_by_range("day")
                        today_dur = today_stats.get("total_duration", 0)
                        self.budget_enforcer.check()
                        self.break_reminder.check(get_break_reminder_minutes())
                    except Exception:
                        pass
                    self._warn_if_no_input_access()

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

                # Rewrite only when something a reader shows changed (seconds_since_input ticks every
                # second), plus a 5 s heartbeat so readers can tell a live daemon from a dead one's file
                state = json.dumps({k: v for k, v in metrics.items() if k != "seconds_since_input"}, sort_keys=True)
                if state != last_state or time.monotonic() - last_write >= 5 or not STATE_FILE.exists():
                    temp_file = STATE_DIR / "live_state.tmp"
                    try:
                        with open(temp_file, "w") as f:
                            json.dump(metrics, f)
                        temp_file.replace(STATE_FILE)
                        last_state, last_write = state, time.monotonic()
                    except Exception:
                        pass

                loop_count += 1
                time.sleep(1.0)
        finally:
            self.stop()

    def _sync_focus_session(self):
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

    def _warn_if_no_input_access(self):
        # Once per run: the journal gets the fix, the desktop gets a notification
        if self.tracker.input_access_denied and not self._warned_input_access:
            self._warned_input_access = True
            print(f"[QHealth Daemon] WARNING: {INPUT_ACCESS_HELP}")
            send_notification("QHealth — No Keyboard/Mouse Access", INPUT_ACCESS_HELP, urgency="critical")

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

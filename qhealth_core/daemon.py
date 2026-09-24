import os
import json
import time
import signal
import sys
from pathlib import Path
from .tracker import ActivityTracker
from .db import init_db, is_paused_setting, get_stats_by_range, vacuum_and_cleanup_db
from .wellbeing import BudgetEnforcer

STATE_DIR = Path.home() / ".local" / "share" / "qhealth"
STATE_FILE = STATE_DIR / "live_state.json"
PID_FILE = STATE_DIR / "daemon.pid"

class QHealthDaemon:
    def __init__(self):
        self.running = False
        self._lock_file = None
        init_db()
        self.tracker = ActivityTracker()
        self.budget_enforcer = BudgetEnforcer(self.tracker)

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

        loop_count = 0
        today_dur = 0
        today_stats = {}
        try:
            while self.running:
                # Sync paused state with DB setting
                self.tracker.paused = is_paused_setting()

                # Refresh today duration and budget alerts every 5 iterations
                if loop_count % 5 == 0:
                    try:
                        today_stats = get_stats_by_range("day")
                        today_dur = today_stats.get("total_duration", 0)
                        self.budget_enforcer.check()
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

                temp_file = STATE_DIR / "live_state.tmp"
                try:
                    with open(temp_file, "w") as f:
                        json.dump(metrics, f)
                    temp_file.replace(STATE_FILE)
                except Exception:
                    pass

                loop_count += 1
                time.sleep(1.0)
        finally:
            self.stop()

    def _handle_signal(self, signum, frame):
        self.running = False

    def stop(self):
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

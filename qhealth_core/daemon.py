import os
import json
import time
import signal
import sys
import datetime
import subprocess
from pathlib import Path
from .tracker import ActivityTracker
from .db import init_db, is_paused_setting, get_stats_by_range, get_all_app_budgets

STATE_DIR = Path.home() / ".local" / "share" / "qhealth"
STATE_FILE = STATE_DIR / "live_state.json"
PID_FILE = STATE_DIR / "daemon.pid"

class QHealthDaemon:
    def __init__(self):
        self.running = False
        self.notified_budget_alerts = set()
        init_db()
        self.tracker = ActivityTracker()

    def start(self):
        self.running = True
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Write PID file
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

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
                        self._check_budget_limits(today_stats)
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

    def _check_budget_limits(self, stats: dict):
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        budgets = get_all_app_budgets()
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
                self._send_notification(
                    f"QHealth — Daily Budget Exceeded",
                    f"{app_name} limit reached ({int(dur_mins)}m / {limit_mins}m)!"
                )

    def _send_notification(self, title: str, message: str):
        try:
            icon_path = str(Path.home() / ".local" / "share" / "icons" / "qhealth.svg")
            subprocess.run([
                "notify-send",
                "-a", "QHealth",
                "-i", icon_path if os.path.exists(icon_path) else "qhealth",
                "-u", "normal",
                title,
                message
            ], timeout=3)
        except Exception:
            pass

    def _handle_signal(self, signum, frame):
        self.running = False

    def stop(self):
        self.running = False
        self.tracker.stop()
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)
        if STATE_FILE.exists():
            STATE_FILE.unlink(missing_ok=True)
        print("[QHealth Daemon] Stopped cleanly.")

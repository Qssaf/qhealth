import os
import json
import time
import signal
import sys
from pathlib import Path
from .tracker import ActivityTracker
from .db import init_db, is_paused_setting, get_stats_by_range

STATE_DIR = Path.home() / ".local" / "share" / "qhealth"
STATE_FILE = STATE_DIR / "live_state.json"
PID_FILE = STATE_DIR / "daemon.pid"

class QHealthDaemon:
    def __init__(self):
        self.running = False
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
        try:
            while self.running:
                # Sync paused state with DB setting
                self.tracker.paused = is_paused_setting()

                # Refresh today duration every 5 iterations
                if loop_count % 5 == 0:
                    try:
                        stats = get_stats_by_range("day")
                        today_dur = stats.get("total_duration", 0)
                    except Exception:
                        pass

                # Update live state file for GUI & Plasma widget every 1 second
                metrics = self.tracker.get_live_metrics()
                metrics["today_duration_seconds"] = today_dur
                hrs = today_dur // 3600
                mins = (today_dur % 3600) // 60
                metrics["today_duration_formatted"] = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"

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
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)
        if STATE_FILE.exists():
            STATE_FILE.unlink(missing_ok=True)
        print("[QHealth Daemon] Stopped cleanly.")

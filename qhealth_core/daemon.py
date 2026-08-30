import os
import json
import time
import signal
import sys
from pathlib import Path
from .tracker import ActivityTracker
from .db import init_db, is_paused_setting

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

        try:
            while self.running:
                # Sync paused state with DB setting
                self.tracker.paused = is_paused_setting()

                # Update live state file for GUI every 1 second
                metrics = self.tracker.get_live_metrics()
                temp_file = STATE_DIR / "live_state.tmp"
                try:
                    with open(temp_file, "w") as f:
                        json.dump(metrics, f)
                    temp_file.replace(STATE_FILE)
                except Exception:
                    pass
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

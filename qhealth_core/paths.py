"""Per-user data location: %LOCALAPPDATA%\\QHealth on Windows, ~/.local/share/qhealth elsewhere."""
import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"


def _data_dir() -> Path:
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "QHealth"
    return Path.home() / ".local" / "share" / "qhealth"


DATA_DIR = _data_dir()
STATE_FILE = DATA_DIR / "live_state.json"  # live metrics the daemon publishes for the GUI / panel widget
PID_FILE = DATA_DIR / "daemon.pid"

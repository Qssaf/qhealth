"""Desktop notifications: notify-send on Linux; on Windows the tray app registers a handler."""
import subprocess
from typing import Callable, Optional

from .paths import IS_WINDOWS

_handler: Optional[Callable[[str, str, bool], None]] = None


def set_handler(handler: Optional[Callable[[str, str, bool], None]]) -> None:
    """handler(title, message, critical) — must be safe to call from any thread."""
    global _handler
    _handler = handler


def send(title: str, message: str, critical: bool = False) -> None:
    if _handler is not None:
        try:
            _handler(title, message, critical)
        except Exception:
            pass
        return
    if IS_WINDOWS:
        return  # no tray running (e.g. tests): nothing to show
    try:
        subprocess.run(
            ["notify-send", "-a", "QHealth", "-i", "qhealth", "-u", "critical" if critical else "normal", title, message],
            timeout=3, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass

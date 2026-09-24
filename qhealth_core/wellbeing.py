import os
import time
import datetime
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from .db import get_budget_usage
from .app_resolver import app_resolver
from .blocker import force_close_app, send_block_notification

# Highest first: when usage jumps past several thresholds at once, only the highest is announced
BUDGET_ALERT_LEVELS = ("100", "1min", "80")

# An input-free stretch this long counts as having taken a break
BREAK_RESET_SECONDS = 5 * 60


def send_notification(title: str, message: str, urgency: str = "normal"):
    try:
        icon_path = str(Path.home() / ".local" / "share" / "icons" / "qhealth.svg")
        subprocess.run([
            "notify-send",
            "-a", "QHealth",
            "-i", icon_path if os.path.exists(icon_path) else "qhealth",
            "-u", urgency,
            title,
            message
        ], timeout=3)
    except Exception:
        pass


class BudgetEnforcer:
    """
    Daily budget warnings and force-close enforcement. Shared by the daemon and by the GUI
    when it tracks on its own (no daemon), so both behave the same.
    """

    def __init__(self, tracker):
        self.tracker = tracker
        self.notified = set()

    def check(self, usage: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
        """Updates the tracker's blocked set, sends threshold alerts and closes exceeded apps.
        Returns the exceeded budgets."""
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        self.notified = {k for k in self.notified if k.startswith(today_str)}
        if usage is None:
            usage = get_budget_usage(today_str)

        exceeded = {
            a_id: info for a_id, info in usage.items()
            if info["used_seconds"] >= info["effective_limit_minutes"] * 60
        }
        self.tracker.update_blocked_apps(exceeded)

        for a_id, info in usage.items():
            limit_mins = info["effective_limit_minutes"]
            limit_secs = limit_mins * 60
            used_secs = info["used_seconds"]
            block = info["block_on_exceed"]
            app_name = app_resolver.resolve(a_id)["display_name"]
            # Keyed by the effective limit so a "+15 min" extension re-arms the warnings
            key_prefix = f"{today_str}_{a_id}_{limit_mins}"

            if used_secs >= limit_secs:
                level = "100"
            elif limit_mins > 1 and limit_secs - used_secs <= 60:
                level = "1min"
            elif used_secs >= limit_secs * 0.8:
                level = "80"
            else:
                level = None

            if level and f"{key_prefix}_{level}" not in self.notified:
                for lower in BUDGET_ALERT_LEVELS[BUDGET_ALERT_LEVELS.index(level):]:
                    self.notified.add(f"{key_prefix}_{lower}")
                self._announce(level, app_name, a_id, int(used_secs // 60), limit_mins, block)

            if a_id in exceeded and block:
                self._enforce(a_id, app_name, f"{key_prefix}_kill")

        return exceeded

    def _announce(self, level: str, app_name: str, a_id: str, used_mins: int, limit_mins: int, block: bool):
        if level == "80":
            send_notification(
                "QHealth — 80% Limit Warning",
                f"You have used {app_name} for {used_mins}m (Daily budget: {limit_mins}m)."
            )
        elif level == "1min":
            if block:
                msg = f"{app_name} will be closed in about 1 minute (daily limit {limit_mins}m)."
            else:
                msg = f"About 1 minute left of your {limit_mins}m daily budget for {app_name}."
            send_notification("QHealth — 1 Minute Left", msg)
        elif block:
            send_block_notification(app_name, limit_mins, a_id, is_reopen=False)
        else:
            send_notification(
                "QHealth — Daily Budget Exceeded",
                f"{app_name} limit reached ({used_mins}m / {limit_mins}m)!"
            )

    def _enforce(self, a_id: str, app_name: str, kill_key: str):
        # Kill the app when it first exceeds, or whenever it is focused again.
        # Re-opens are caught instantly by the tracker's focus hook, so there is no need
        # to rescan /proc for every exceeded app on every check.
        tracker = self.tracker
        cur_pid = None
        is_focused = False
        with tracker.window_lock:
            cur_app_id = tracker.resolved_app_info.get("app_id", "").lower()
            cur_raw = tracker.current_raw_app.lower()
            if cur_app_id == a_id or (cur_raw and (
                cur_raw == a_id or a_id.endswith(f".{cur_raw}") or cur_raw.endswith(f".{a_id}")
            )):
                is_focused = True
                cur_pid = tracker.current_pid or None
                tracker.current_raw_app = ""
                tracker.current_title = ""
                tracker.current_class = ""
                tracker.current_pid = 0
                tracker.resolved_app_info = app_resolver.resolve("")
        if is_focused or kill_key not in self.notified:
            self.notified.add(kill_key)
            force_close_app(a_id, app_name, cur_pid)


class BreakReminder:
    """Reminds the user to take a break after N minutes of activity without a 5-minute pause."""

    def __init__(self, tracker):
        self.tracker = tracker
        self.streak_start: Optional[float] = None

    def check(self, interval_minutes: int, now: Optional[float] = None) -> bool:
        """Returns True when a reminder was sent."""
        now = time.monotonic() if now is None else now
        if interval_minutes <= 0 or self.tracker.paused or now - self.tracker.last_input_time >= BREAK_RESET_SECONDS:
            self.streak_start = None
            return False
        if self.streak_start is None:
            self.streak_start = now
            return False
        if now - self.streak_start < interval_minutes * 60:
            return False
        self.streak_start = now
        send_notification(
            "QHealth — Time for a Break",
            f"You've been active for {interval_minutes} minutes. Look away from the screen, "
            "stretch and move around for a few minutes."
        )
        return True

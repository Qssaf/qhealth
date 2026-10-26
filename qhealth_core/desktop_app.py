import os
import sys
import datetime
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu
)
from PyQt6.QtGui import QAction

from .tracker import ActivityTracker
from . import notify
from .paths import IS_WINDOWS, PID_FILE
from .db import (
    toggle_pause_setting, is_paused_setting, get_stats_by_range, get_focus_session, data_version,
    get_break_reminder_minutes, set_break_reminder_minutes, DEFAULT_BREAK_REMINDER_MINUTES,
    export_data_to_json, export_data_to_csv
)
from qhealth_gui.main_window import QHealthMainWindow, create_app_icon
from qhealth_gui.utils import format_duration, format_number

def _single_instance_socket_name() -> str:
    # Per user: a fixed name in /tmp (or a global named pipe on Windows) is shared by every account
    if IS_WINDOWS:
        return f"qhealth_single_instance_{os.environ.get('USERNAME', 'user')}"
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir and os.path.isdir(runtime_dir):
        return os.path.join(runtime_dir, "qhealth.sock")
    return f"qhealth_single_instance_{os.getuid()}"

SOCKET_NAME = _single_instance_socket_name()


class _TrayNotifier(QObject):
    """Carries notifications raised on tracker threads over to the GUI thread's tray icon."""
    message = pyqtSignal(str, str, bool)


def is_daemon_running() -> bool:
    if IS_WINDOWS:
        return False  # no separate daemon on Windows: the tray app tracks
    # A stale PID file (daemon killed with SIGKILL) may point at a recycled PID,
    # so also confirm that process really is a QHealth daemon.
    try:
        pid = int(PID_FILE.read_text().strip())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            args = f.read().decode("utf-8", errors="ignore").split("\x00")
        return "--daemon" in args or "-d" in args
    except (OSError, ValueError):
        return False

class QHealthApp:
    def __init__(self):
        if IS_WINDOWS:
            from . import win32
            win32.set_app_user_model_id()  # must precede any window so the taskbar shows QHealth's icon
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setApplicationName("QHealth")
        self.app.setDesktopFileName("qhealth")

        self.icon = create_app_icon()
        self.app.setWindowIcon(self.icon)

        # 1. Single Instance Check
        self.local_server = None
        if not self._check_single_instance():
            sys.exit(0)

        self.daemon = None
        self.daemon_active = is_daemon_running()
        if IS_WINDOWS:
            # Windows has no user-session service manager that can see the desktop, so the tray app
            # runs the daemon loop itself (budgets, focus sessions, live state) for as long as it is open
            from .daemon import QHealthDaemon
            self.daemon = QHealthDaemon()
            self.daemon.start_embedded()
            self.tracker = self.daemon.tracker
        elif not self.daemon_active:
            from .wellbeing import BudgetEnforcer, BreakReminder
            self.tracker = ActivityTracker()
            # Same budget enforcement and break reminders the daemon would provide
            self.budget_enforcer = BudgetEnforcer(self.tracker)
            self.break_reminder = BreakReminder(self.tracker)
            self._run_wellbeing_checks()
            self.tracker.start()
            self._block_sync_timer = QTimer()
            self._block_sync_timer.timeout.connect(self._sync_standalone_tracker)
            self._block_sync_timer.start(5000)
        else:
            self.tracker = None

        # 3. Create Main Window
        self.window = QHealthMainWindow(self.tracker)
        self.window.on_close = self._on_window_closed
        self._tray_hint_shown = False

        # 4. Create System Tray
        self._setup_tray()

    def _check_single_instance(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(SOCKET_NAME)
        if socket.waitForConnected(200):
            socket.write(b"SHOW\n")
            socket.waitForBytesWritten(200)
            socket.disconnectFromServer()
            return False

        QLocalServer.removeServer(SOCKET_NAME)
        self.local_server = QLocalServer()
        self.local_server.newConnection.connect(self._handle_local_connection)
        self.local_server.listen(SOCKET_NAME)
        return True

    def _handle_local_connection(self):
        client = self.local_server.nextPendingConnection()
        if client:
            client.waitForReadyRead(200)
            msg = bytes(client.readAll()).decode("utf-8").strip()
            if msg == "SHOW":
                self.show_window()
            client.disconnectFromServer()

    def _sync_standalone_tracker(self):
        if is_daemon_running():
            # Daemon started after the GUI: hand tracking over to avoid double-counting
            self._block_sync_timer.stop()
            self.tracker.stop()
            self.tracker = None
            self.window.tracker = None
            return
        self._run_wellbeing_checks()

    def _run_wellbeing_checks(self):
        # PyQt aborts the whole app on an exception escaping a slot; a busy DB must not do that
        try:
            self.budget_enforcer.check()
        except Exception:
            pass
        try:
            self.break_reminder.check(get_break_reminder_minutes())
        except Exception:
            pass
        try:
            self.tracker.update_focus_session(get_focus_session())
        except Exception:
            pass

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self.icon, self.app)
        self.tray.setToolTip("QHealth — Digital Wellbeing & Activity Tracker")

        self.tray_menu = QMenu()

        open_action = QAction("📊 Open QHealth Dashboard", self.app)
        open_action.triggered.connect(self.show_window)
        self.tray_menu.addAction(open_action)

        self.tray_menu.addSeparator()

        # Quick summary stats items (Feature D)
        self.stats_action = QAction("⏱ Today: 0m", self.app)
        self.stats_action.setEnabled(False)
        self.tray_menu.addAction(self.stats_action)

        self.top_app_action = QAction("🏆 Top: —", self.app)
        self.top_app_action.setEnabled(False)
        self.tray_menu.addAction(self.top_app_action)

        self.focus_action = QAction("🎯 Focus Mode: Inactive", self.app)
        self.focus_action.triggered.connect(self._open_focus_dialog)
        self.tray_menu.addAction(self.focus_action)

        self.tray_menu.addSeparator()

        self.pause_action = QAction("Pause Tracking", self.app)
        self.pause_action.triggered.connect(self._toggle_pause)
        self.tray_menu.addAction(self.pause_action)

        self.break_action = QAction(f"Break Reminders (every {DEFAULT_BREAK_REMINDER_MINUTES} min)", self.app)
        self.break_action.setCheckable(True)
        try:
            self.break_action.setChecked(get_break_reminder_minutes() > 0)
        except Exception:
            pass
        self.break_action.toggled.connect(self._toggle_break_reminders)
        self.tray_menu.addAction(self.break_action)

        export_menu = self.tray_menu.addMenu("Export Data")
        json_action = QAction("Full Backup (JSON)…", self.app)
        json_action.triggered.connect(lambda: self._export("json"))
        export_menu.addAction(json_action)
        csv_action = QAction("Activity History (CSV)…", self.app)
        csv_action.triggered.connect(lambda: self._export("csv"))
        export_menu.addAction(csv_action)

        if IS_WINDOWS:
            from . import win32
            self.autostart_action = QAction("Start with Windows", self.app)
            self.autostart_action.setCheckable(True)
            self.autostart_action.setChecked(win32.autostart_enabled())
            self.autostart_action.toggled.connect(win32.set_autostart)
            self.tray_menu.addAction(self.autostart_action)
            # Notifications from the embedded daemon appear as tray balloons / toasts
            self._notifier = _TrayNotifier()
            self._notifier.message.connect(lambda title, msg, critical: self.tray.showMessage(
                title, msg, QSystemTrayIcon.MessageIcon.Warning if critical else QSystemTrayIcon.MessageIcon.Information, 8000))
            notify.set_handler(self._notifier.message.emit)

        self.tray_menu.addSeparator()

        quit_action = QAction("Quit QHealth", self.app)
        quit_action.triggered.connect(self.quit)
        self.tray_menu.addAction(quit_action)

        self.tray.setContextMenu(self.tray_menu)
        self.tray_menu.aboutToShow.connect(self._refresh_tray_stats)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        # Tray refresh timer
        self._tray_version = None
        self._tray_stats = {}
        self.tray_timer = QTimer(self.app)
        self.tray_timer.timeout.connect(self._refresh_tray_stats)
        self.tray_timer.start(15000)
        self._refresh_tray_stats()

    def _open_focus_dialog(self):
        self.show_window()
        if hasattr(self.window, "_open_focus_dialog"):
            self.window._open_focus_dialog()

    def _refresh_tray_stats(self):
        try:
            # Re-aggregate today only when something was written since the last tick
            version = data_version()
            if version != self._tray_version:
                self._tray_stats = get_stats_by_range("day")
                self._tray_version = version
            stats = self._tray_stats
            dur = stats.get("total_duration", 0)
            dur_str = format_duration(dur)
            keys = stats.get("total_keystrokes", 0)
            clicks = stats.get("total_clicks", 0)
            apps = stats.get("apps", [])
            top_name = apps[0]["app_name"] if apps else "None"
            top_pct = apps[0]["percentage"] if apps else 0

            self.stats_action.setText(f"⏱ Today: {dur_str} ({format_number(keys)} keys)")
            self.top_app_action.setText(f"🏆 Top: {top_name} ({top_pct}%)")

            # Update focus action
            focus_session = get_focus_session()
            if focus_session.get("active"):
                rem_secs = focus_session.get("remaining_seconds", 0)
                rem_mins = max(1, (rem_secs + 59) // 60)
                self.focus_action.setText(f"🎯 Focus: {rem_mins}m left (Click to manage)")
            else:
                self.focus_action.setText("🎯 Start Focus Session...")

            # Update tooltip
            paused = is_paused_setting()
            status_text = "PAUSED" if paused else "TRACKING"
            tip = (
                f"QHealth [{status_text}]\n"
                f"⏱ Today: {dur_str}\n"
                f"⌨ {format_number(keys)} keys · 🖱 {format_number(clicks)} clicks\n"
                f"🏆 Top: {top_name} ({top_pct}%)"
            )
            self.tray.setToolTip(tip)
            self.pause_action.setText("Resume Tracking" if paused else "Pause Tracking")
        except Exception:
            pass

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window.isVisible() and not self.window.isMinimized():
                self.window.hide()
            else:
                self.show_window()

    def _toggle_pause(self):
        new_paused = toggle_pause_setting()
        if self.tracker:
            self.tracker.paused = new_paused
        self.pause_action.setText("Resume Tracking" if new_paused else "Pause Tracking")
        self.window.btn_pause.setText("Resume" if new_paused else "Pause")
        self.window.btn_pause.setChecked(new_paused)

    def _toggle_break_reminders(self, enabled: bool):
        try:
            set_break_reminder_minutes(DEFAULT_BREAK_REMINDER_MINUTES if enabled else 0)
        except Exception:
            pass

    def _export(self, kind: str):
        from PyQt6.QtWidgets import QFileDialog
        stamp = datetime.date.today().isoformat()
        name = f"qhealth-backup-{stamp}.json" if kind == "json" else f"qhealth-history-{stamp}.csv"
        file_filter = "JSON (*.json)" if kind == "json" else "CSV (*.csv)"
        path, _ = QFileDialog.getSaveFileName(None, "Export QHealth Data", str(Path.home() / name), file_filter)
        if not path:
            return
        try:
            if kind == "json":
                export_data_to_json(path)
            else:
                export_data_to_csv(path)
            self.tray.showMessage("QHealth", f"Exported to {path}", QSystemTrayIcon.MessageIcon.Information, 4000)
        except Exception as e:
            self.tray.showMessage("QHealth", f"Export failed: {e}", QSystemTrayIcon.MessageIcon.Warning, 6000)

    def _on_window_closed(self):
        if self.tracker is None:
            # Viewer only: the daemon keeps tracking, so nothing needs to stay resident
            self.quit()
        elif not self._tray_hint_shown:
            # This process is the tracker (no daemon / Windows), so closing must not stop it, but say so
            self._tray_hint_shown = True
            self.tray.showMessage(
                "QHealth is still tracking",
                "QHealth keeps tracking from the tray. Use Quit in the tray menu to stop.",
                QSystemTrayIcon.MessageIcon.Information, 6000
            )

    def show_window(self):
        self.window.show()
        self.window.setWindowState(self.window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.window.raise_()
        self.window.activateWindow()

    def quit(self):
        if self.local_server:
            self.local_server.close()
            QLocalServer.removeServer(SOCKET_NAME)
        notify.set_handler(None)
        if self.daemon:
            self.daemon.stop()
        elif self.tracker:
            self.tracker.stop()
        self.app.quit()

    def run(self, show_gui: bool = True):
        if show_gui:
            self.show_window()
        return self.app.exec()

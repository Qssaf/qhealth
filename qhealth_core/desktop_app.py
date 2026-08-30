import os
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu
)
from PyQt6.QtGui import QIcon, QAction

from .tracker import ActivityTracker
from qhealth_gui.main_window import QHealthMainWindow, create_app_icon

SOCKET_NAME = "qhealth_single_instance_socket"

class QHealthApp:
    def __init__(self):
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

        # 2. Start Tracker
        self.tracker = ActivityTracker()
        self.tracker.start()

        # 3. Create Main Window
        self.window = QHealthMainWindow(self.tracker)

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

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self.icon, self.app)
        self.tray.setToolTip("QHealth — Screen Time & Activity Tracker")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a;
                color: #f1f5f9;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: rgba(16, 185, 129, 0.2);
                color: #34d399;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 4px 8px;
            }
        """)

        open_action = QAction("Open QHealth", self.app)
        open_action.triggered.connect(self.show_window)
        menu.addAction(open_action)

        self.pause_action = QAction("Pause Tracking", self.app)
        self.pause_action.triggered.connect(self._toggle_pause)
        menu.addAction(self.pause_action)

        menu.addSeparator()

        quit_action = QAction("Quit QHealth", self.app)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window.isVisible() and not self.window.isMinimized():
                self.window.hide()
            else:
                self.show_window()

    def _toggle_pause(self):
        is_paused = self.tracker.toggle_pause()
        self.pause_action.setText("Resume Tracking" if is_paused else "Pause Tracking")
        self.window.btn_pause.setText("Resume" if is_paused else "Pause")
        self.window.btn_pause.setChecked(is_paused)

    def show_window(self):
        self.window.show()
        self.window.setWindowState(self.window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.window.raise_()
        self.window.activateWindow()

    def quit(self):
        if self.local_server:
            self.local_server.close()
            QLocalServer.removeServer(SOCKET_NAME)
        self.tracker.stop()
        self.app.quit()

    def run(self, show_gui: bool = True):
        if show_gui:
            self.show_window()
        return self.app.exec()

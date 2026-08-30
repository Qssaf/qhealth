#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

def main():
    parser = argparse.ArgumentParser(description="QHealth — Linux Screen Time & Activity Tracker")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run 24/7 background tracking daemon")
    args = parser.parse_args()

    if args.daemon:
        from qhealth_core.daemon import QHealthDaemon
        daemon = QHealthDaemon()
        daemon.start()
    else:
        from PyQt6.QtWidgets import QApplication
        from qhealth_gui.main_window import QHealthMainWindow, create_app_icon

        app = QApplication(sys.argv)
        app.setApplicationName("QHealth")
        app.setDesktopFileName("qhealth")
        app.setWindowIcon(create_app_icon())

        window = QHealthMainWindow()
        window.show()
        sys.exit(app.exec())

if __name__ == "__main__":
    main()

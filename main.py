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
        from qhealth_core.desktop_app import QHealthApp
        app = QHealthApp()
        sys.exit(app.run(show_gui=True))

if __name__ == "__main__":
    main()

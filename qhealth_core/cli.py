"""`qhealth` command: opens the dashboard, or runs the tracking daemon with --daemon."""
import argparse
import sys

from . import __version__


def main():
    parser = argparse.ArgumentParser(prog="qhealth", description="QHealth — screen time & activity tracker")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run 24/7 background tracking daemon")
    parser.add_argument("--minimized", action="store_true", help="Start in the tray without opening the window (used at login)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    if args.daemon:
        if sys.platform == "win32":
            parser.exit(2, "qhealth: on Windows tracking runs inside the tray app; start it with `qhealth --minimized`.\n")
        from .daemon import QHealthDaemon
        QHealthDaemon().start()
    else:
        sys.argv[0] = "qhealth"  # X11 WM_CLASS res_name, matched by StartupWMClass in the .desktop file
        from .desktop_app import QHealthApp
        sys.exit(QHealthApp().run(show_gui=not args.minimized))


if __name__ == "__main__":
    main()

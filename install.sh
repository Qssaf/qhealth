#!/usr/bin/env bash
# Install QHealth on any Linux distro.
#
#   ./install.sh                      install for the current user into ~/.local (no root needed)
#   ./install.sh --enable             ... and enable + start the background tracking service
#   ./install.sh --uninstall          remove it again (your activity history is kept)
#   sudo PREFIX=/usr/local ./install.sh   system-wide install
#
# Arch / CachyOS users can build a native package instead: packaging/arch/PKGBUILD
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
BIN="$PREFIX/bin"
LIB="$PREFIX/lib/qhealth"
DATA="$PREFIX/share"
if [ "$PREFIX" = "$HOME/.local" ]; then
    USER_INSTALL=1
    UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
else
    USER_INSTALL=0
    UNIT_DIR="$PREFIX/lib/systemd/user"
fi

FILES=(
    "$BIN/qhealth"
    "$DATA/applications/qhealth.desktop"
    "$DATA/icons/hicolor/scalable/apps/qhealth.svg"
    "$DATA/metainfo/qhealth.metainfo.xml"
    "$UNIT_DIR/qhealth.service"
)

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m==>\033[0m %s\n' "$*" >&2; }

user_systemctl() {
    # Only meaningful for the invoking user's session; skipped quietly where there is none (e.g. sudo, CI)
    [ "$USER_INSTALL" = 1 ] && systemctl --user "$@" 2>/dev/null
}

refresh_caches() {
    command -v update-desktop-database >/dev/null && update-desktop-database -q "$DATA/applications" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA/icons/hicolor" 2>/dev/null || true
    command -v kbuildsycoca6 >/dev/null && [ "$USER_INSTALL" = 1 ] && kbuildsycoca6 >/dev/null 2>&1 || true
}

uninstall() {
    user_systemctl disable --now qhealth.service || true
    rm -f "${FILES[@]}"
    rm -rf "$LIB" "$DATA/plasma/plasmoids/org.kde.plasma.qhealth"
    user_systemctl daemon-reload || true
    refresh_caches
    say "QHealth removed. Your history is still in ~/.local/share/qhealth (delete that folder to erase it)."
}

check_requirements() {
    if ! command -v python3 >/dev/null; then
        warn "python3 is required."; exit 1
    fi
    if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
        warn "Python 3.10 or newer is required (found $(python3 -V 2>&1))."; exit 1
    fi
    if ! python3 -c 'import PyQt6.QtWidgets, PyQt6.QtSvg' 2>/dev/null; then
        warn "PyQt6 (with SVG support) is missing. Install it with your package manager:"
        warn "  Arch/CachyOS:  sudo pacman -S python-pyqt6 qt6-svg"
        warn "  Fedora:        sudo dnf install python3-pyqt6"
        warn "  Debian/Ubuntu: sudo apt install python3-pyqt6 python3-pyqt6.qtsvg"
        exit 1
    fi
    command -v notify-send >/dev/null || warn "notify-send not found: limit/focus notifications will be silent (install libnotify)."
}

install_app() {
    check_requirements
    local was_running=0
    user_systemctl is-active --quiet qhealth.service && was_running=1

    say "Installing QHealth $(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/qhealth_core/__init__.py") into $PREFIX"
    rm -rf "$LIB"
    mkdir -p "$LIB" "$BIN"
    cp -r "$SRC/qhealth_core" "$SRC/qhealth_gui" "$LIB/"
    find "$LIB" -name __pycache__ -type d -prune -exec rm -rf {} +
    python3 -m compileall -q "$LIB" >/dev/null || true

    cat > "$BIN/qhealth" <<EOF
#!/bin/sh
export PYTHONPATH="$LIB\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m qhealth_core.cli "\$@"
EOF
    chmod 755 "$BIN/qhealth"

    # Absolute paths: ~/.local/bin is not always on the PATH of the desktop session or systemd
    mkdir -p "$DATA/applications" "$UNIT_DIR"
    sed -e "s|^Exec=qhealth|Exec=$BIN/qhealth|" -e "s|^TryExec=qhealth|TryExec=$BIN/qhealth|" \
        "$SRC/packaging/linux/qhealth.desktop" > "$DATA/applications/qhealth.desktop"
    sed -e "s|^ExecStart=/usr/bin/qhealth|ExecStart=$BIN/qhealth|" \
        "$SRC/packaging/linux/qhealth.service" > "$UNIT_DIR/qhealth.service"
    chmod 644 "$DATA/applications/qhealth.desktop" "$UNIT_DIR/qhealth.service"
    install -Dm644 "$SRC/assets/qhealth.svg" "$DATA/icons/hicolor/scalable/apps/qhealth.svg"
    install -Dm644 "$SRC/packaging/linux/qhealth.metainfo.xml" "$DATA/metainfo/qhealth.metainfo.xml"
    rm -rf "$DATA/plasma/plasmoids/org.kde.plasma.qhealth"
    mkdir -p "$DATA/plasma/plasmoids"
    cp -r "$SRC/plasma_plasmoid/org.kde.plasma.qhealth" "$DATA/plasma/plasmoids/"

    refresh_caches
    user_systemctl daemon-reload || true

    if [ "$ENABLE" = 1 ]; then
        # reenable drops [Install] links left by older unit files before adding the current ones
        { user_systemctl reenable qhealth.service && user_systemctl restart qhealth.service; } \
            && say "Background tracking enabled and running on this version." \
            || warn "Could not enable the service; run: systemctl --user enable --now qhealth.service"
    elif [ "$was_running" = 1 ]; then
        user_systemctl restart qhealth.service && say "Restarted the running tracking service on the new version."
    fi

    say "Done. Launch \"QHealth\" from your app menu, or run: $BIN/qhealth"
    [ "$ENABLE" = 1 ] || [ "$was_running" = 1 ] || say "Start 24/7 tracking with: systemctl --user enable --now qhealth.service"
    if ! id -nG | tr ' ' '\n' | grep -qx input; then
        warn "Keyboard/mouse tracking needs read access to /dev/input. Run:"
        warn "  sudo usermod -aG input \"\$USER\"   then log out and back in."
    fi
    case ":$PATH:" in *":$BIN:"*) ;; *) warn "$BIN is not on your PATH; the app menu entry still works." ;; esac
}

ENABLE=0
ACTION=install
for arg in "$@"; do
    case "$arg" in
        --enable) ENABLE=1 ;;
        --uninstall) ACTION=uninstall ;;
        -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) warn "Unknown option: $arg"; exit 2 ;;
    esac
done

if [ "$ACTION" = uninstall ]; then uninstall; else install_app; fi

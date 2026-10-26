import os
import hashlib
import functools
from PyQt6.QtCore import Qt, QFileInfo
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter, QFont
from PyQt6.QtWidgets import QFileIconProvider
from . import theme

APP_PALETTE = [QColor(c) for c in theme.CATEGORICAL]

ICON_SEARCH_DIRS = [
    "/usr/share/icons/hicolor/64x64/apps",
    "/usr/share/icons/hicolor/128x128/apps",
    "/usr/share/icons/hicolor/scalable/apps",
    "/usr/share/pixmaps",
    os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps"),
    os.path.expanduser("~/.local/share/icons"),
]

CATEGORY_COLORS = {
    "Development": APP_PALETTE[0],
    "Browsing": APP_PALETTE[1],
    "Communication": APP_PALETTE[2],
    "Productivity": APP_PALETTE[3],
    "Media & Design": APP_PALETTE[4],
    "Gaming": APP_PALETTE[6],
    "System": QColor(theme.TEXT_3),
    "Other": QColor(theme.TEXT_2),
}

def get_app_color(app_name: str, index: int = 0) -> QColor:
    if index < len(APP_PALETTE):
        return APP_PALETTE[index]
    h = int(hashlib.md5(app_name.encode('utf-8')).hexdigest(), 16)
    return APP_PALETTE[h % len(APP_PALETTE)]

def get_category_color(name: str) -> QColor:
    if name in CATEGORY_COLORS:
        return CATEGORY_COLORS[name]
    h = int(hashlib.md5(name.encode('utf-8')).hexdigest(), 16)
    return APP_PALETTE[h % len(APP_PALETTE)]

def category_badge_html(category: str) -> str:
    """Rich-text badge body: identity rides on the coloured dot, the text stays in a text token."""
    return f'<span style="color:{get_category_color(category).name()}">●</span>&nbsp;{category}'

def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours == 0:
        return f"{minutes}m"
    return f"{hours}h {minutes}m"

def format_number(num: int) -> str:
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return f"{num:,}"

@functools.lru_cache(maxsize=1)
def _icon_dir_listing():
    listing = []
    for d in ICON_SEARCH_DIRS:
        try:
            names = sorted(n for n in os.listdir(d) if not n.startswith("."))
        except OSError:
            continue
        listing.append((d, names, set(names)))
    return listing

@functools.lru_cache(maxsize=1024)
def get_app_icon_pixmap(icon_name: str, app_name: str, size: int = 32) -> QPixmap:
    """Returns real system icon from KDE theme or direct file paths, or sleek painted fallback."""
    # Windows: apps are identified by their executable, and the shell knows its icon
    if icon_name and icon_name.lower().endswith(".exe") and os.path.isfile(icon_name):
        ico = QFileIconProvider().icon(QFileInfo(icon_name))
        if not ico.isNull():
            return ico.pixmap(size, size)

    candidates = []
    if icon_name:
        candidates.extend([
            icon_name,
            f"{icon_name}.desktop",
            icon_name.replace(".desktop", ""),
            icon_name.lower(),
            f"org.kde.{icon_name}"
        ])
    if app_name:
        candidates.extend([
            app_name.lower(),
            app_name.lower().replace(" ", "-"),
            f"ai.{app_name.lower()}.desktop"
        ])

    # 1. Try Qt Theme
    for cand in candidates:
        ico = QIcon.fromTheme(cand)
        if not ico.isNull():
            return ico.pixmap(size, size)

    # 2. Check icon file paths directly (against a one-time directory listing, not per-call globbing)
    for d, names, name_set in _icon_dir_listing():
        for cand in candidates:
            for ext in [".png", ".svg", ".xpm", ""]:
                if f"{cand}{ext}" in name_set:
                    ico = QIcon(os.path.join(d, f"{cand}{ext}"))
                    if not ico.isNull():
                        return ico.pixmap(size, size)
            match = next((n for n in names if cand in n), None)
            if match:
                ico = QIcon(os.path.join(d, match))
                if not ico.isNull():
                    return ico.pixmap(size, size)

    # 3. Fallback: clean modern tile with app initial
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor(theme.HOVER))
    painter.setPen(QColor(theme.BORDER_STRONG))
    painter.drawRoundedRect(1, 1, size - 2, size - 2, size * 0.25, size * 0.25)

    painter.setPen(QColor(theme.TEXT))
    painter.setFont(theme.font(max(8, int(size * 0.44)), QFont.Weight.DemiBold))
    initial = app_name[0].upper() if app_name else "?"
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, initial)
    painter.end()

    return pixmap

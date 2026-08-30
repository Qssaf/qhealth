import os
import glob
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter, QFont

CATEGORY_COLORS = {
    "Development": QColor("#10b981"),
    "Gaming": QColor("#f43f5e"),
    "Browsing": QColor("#06b6d4"),
    "Communication": QColor("#6366f1"),
    "Media & Design": QColor("#f59e0b"),
    "Productivity": QColor("#14b8a6"),
    "System": QColor("#64748b"),
    "Other": QColor("#71717a")
}

ICON_SEARCH_DIRS = [
    "/usr/share/icons/hicolor/64x64/apps",
    "/usr/share/icons/hicolor/128x128/apps",
    "/usr/share/icons/hicolor/scalable/apps",
    "/usr/share/pixmaps",
    os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps"),
    os.path.expanduser("~/.local/share/icons"),
]

def get_category_color(category: str) -> QColor:
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS["Other"])

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

def get_app_icon_pixmap(icon_name: str, app_name: str, size: int = 32) -> QPixmap:
    """Returns real system icon from KDE theme or direct file paths, or sleek painted fallback."""
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

    # 2. Check icon file paths directly
    for d in ICON_SEARCH_DIRS:
        if not os.path.exists(d):
            continue
        for cand in candidates:
            # Check exact candidate filename
            for ext in [".png", ".svg", ".xpm", ""]:
                exact_path = os.path.join(d, f"{cand}{ext}")
                if os.path.exists(exact_path):
                    ico = QIcon(exact_path)
                    if not ico.isNull():
                        return ico.pixmap(size, size)
            # Wildcard search
            matches = glob.glob(os.path.join(d, f"*{cand}*"))
            if matches:
                ico = QIcon(matches[0])
                if not ico.isNull():
                    return ico.pixmap(size, size)

    # 3. Fallback: clean modern tile with app initial
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor(30, 41, 59))
    painter.setPen(QColor(51, 65, 85))
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 6, 6)

    painter.setPen(QColor("#f8fafc"))
    font = QFont("Inter", int(size * 0.42), QFont.Weight.Bold)
    painter.setFont(font)
    initial = app_name[0].upper() if app_name else "?"
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, initial)
    painter.end()

    return pixmap

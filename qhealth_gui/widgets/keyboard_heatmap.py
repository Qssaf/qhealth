from typing import Dict, Any, List, Tuple
from PyQt6.QtCore import Qt, QRectF, QPoint
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolTip, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from ..utils import format_number

KEYBOARD_ROWS: List[List[Tuple[int, str, float]]] = [
    # Row 0: Number row (14.8u total)
    [
        (1, "ESC", 1.0), (2, "1", 1.0), (3, "2", 1.0), (4, "3", 1.0), (5, "4", 1.0),
        (6, "5", 1.0), (7, "6", 1.0), (8, "7", 1.0), (9, "8", 1.0), (10, "9", 1.0),
        (11, "0", 1.0), (12, "-", 1.0), (13, "=", 1.0), (14, "BACK", 1.8)
    ],
    # Row 1: QWERTY (14.8u total)
    [
        (15, "TAB", 1.4), (16, "Q", 1.0), (17, "W", 1.0), (18, "E", 1.0), (19, "R", 1.0),
        (20, "T", 1.0), (21, "Y", 1.0), (22, "U", 1.0), (23, "I", 1.0), (24, "O", 1.0),
        (25, "P", 1.0), (26, "[", 1.0), (27, "]", 1.0), (43, "\\", 1.4)
    ],
    # Row 2: ASDF (14.8u total)
    [
        (58, "CAPS", 1.7), (30, "A", 1.0), (31, "S", 1.0), (32, "D", 1.0), (33, "F", 1.0),
        (34, "G", 1.0), (35, "H", 1.0), (36, "J", 1.0), (37, "K", 1.0), (38, "L", 1.0),
        (39, ";", 1.0), (40, "'", 1.0), (28, "ENTER", 2.1)
    ],
    # Row 3: ZXCV with Up Arrow (14.8u total)
    [
        (42, "SHIFT", 2.2), (44, "Z", 1.0), (45, "X", 1.0), (46, "C", 1.0), (47, "V", 1.0),
        (48, "B", 1.0), (49, "N", 1.0), (50, "M", 1.0), (51, ",", 1.0), (52, ".", 1.0),
        (53, "/", 1.0), (54, "SHIFT", 1.6), (103, "↑", 1.0)
    ],
    # Row 4: Bottom row with Left/Down/Right Arrows (14.8u total)
    [
        (29, "CTRL", 1.2), (125, "SUPER", 1.0), (56, "ALT", 1.0),
        (57, "SPACEBAR", 6.6),
        (100, "ALT", 1.0), (97, "CTRL", 1.0),
        (105, "←", 1.0), (108, "↓", 1.0), (106, "→", 1.0)
    ]
]

class KeyboardPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.key_counts: Dict[int, int] = {}
        self.setMouseTracking(True)
        self.key_rects = []

    def set_data(self, key_counts: Dict[int, int]):
        self.key_counts = key_counts
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        total_keys = sum(self.key_counts.values())
        for rect, code, label, count in self.key_rects:
            if rect.contains(pos.x(), pos.y()):
                pct = round((count / total_keys * 100), 1) if total_keys > 0 else 0.0
                tip = f"⌨ Key: {label}\nPresses: {format_number(count)} ({pct}%)"
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.key_rects = []
        w = float(self.width())
        h = float(self.height())

        total_units = 14.8
        row_count = 5.0
        gap = max(2.5, min(5.0, w / 200.0))

        # Compute key dimensions that best fill width and height
        avail_w = w - 16.0
        avail_h = h - 16.0

        unit_w = (avail_w - (total_units * gap)) / total_units
        unit_h = (avail_h - (row_count * gap)) / row_count

        # Maintain balanced keycap aspect ratio
        key_h = max(20.0, min(unit_h, unit_w * 1.15))
        key_unit_w = (avail_w - (total_units * gap)) / total_units

        total_kb_w = total_units * key_unit_w + (total_units - 1.0) * gap
        total_kb_h = row_count * key_h + (row_count - 1.0) * gap

        x_start = max(8.0, (w - total_kb_w) / 2.0)
        y_start = max(8.0, (h - total_kb_h) / 2.0)

        max_count = max(self.key_counts.values()) if self.key_counts else 1
        if max_count == 0:
            max_count = 1

        for r_idx, row in enumerate(KEYBOARD_ROWS):
            x_cursor = x_start
            y_pos = y_start + r_idx * (key_h + gap)

            for code, label, width_u in row:
                key_w = width_u * key_unit_w + (width_u - 1.0) * gap
                rect = QRectF(x_cursor, y_pos, key_w, key_h)
                count = self.key_counts.get(code, 0)
                self.key_rects.append((rect, code, label, count))

                # Compute key color intensity
                if count == 0:
                    bg_color = QColor("#111827")
                    border_color = QColor("#1f293d")
                    text_color = QColor("#64748b")
                else:
                    ratio = count / float(max_count)
                    if ratio < 0.20:
                        bg_color = QColor("#064e3b")
                        border_color = QColor("#047857")
                        text_color = QColor("#a7f3d0")
                    elif ratio < 0.50:
                        bg_color = QColor("#047857")
                        border_color = QColor("#10b981")
                        text_color = QColor("#ffffff")
                    elif ratio < 0.80:
                        bg_color = QColor("#059669")
                        border_color = QColor("#34d399")
                        text_color = QColor("#ffffff")
                    else:
                        bg_color = QColor("#10b981")
                        border_color = QColor("#6ee7b7")
                        text_color = QColor("#ffffff")

                # Paint Keycap
                painter.setBrush(QBrush(bg_color))
                painter.setPen(QPen(border_color, 1.2))
                painter.drawRoundedRect(rect, 4.0, 4.0)

                # Key label
                painter.setPen(text_color)
                f_size = max(7, min(10, int(key_h * 0.28)))
                font = QFont("Inter", f_size, QFont.Weight.Bold if count > 0 else QFont.Weight.Normal)
                painter.setFont(font)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

                x_cursor += key_w + gap

        painter.end()


class KeyboardHeatmapWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("PHYSICAL KEYBOARD HEATMAP")
        title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        self.sub_lbl = QLabel("Live key frequency")
        self.sub_lbl.setStyleSheet("font-size: 10px; color: #64748b; font-family: monospace;")
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(self.sub_lbl)
        lay.addLayout(hdr)

        self.keyboard_painter = KeyboardPainter(self)
        lay.addWidget(self.keyboard_painter, 1)

    def update_data(self, key_counts: Dict[int, int], range_type: str = "day"):
        sub_map = {
            "day": "Day's key frequency",
            "week": "Last 7 days key frequency",
            "month": "Last 30 days key frequency",
            "year": "This year's key frequency",
            "all_time": "Lifetime key frequency"
        }
        self.sub_lbl.setText(sub_map.get(range_type, "Key frequency"))
        self.keyboard_painter.set_data(key_counts)

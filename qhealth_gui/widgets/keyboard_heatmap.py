import math
from typing import Dict, List, Tuple
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QToolTip, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QFont, QPen
from .. import theme as t
from ..utils import format_number
from .common import RampLegend, card_header

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
        (57, "SPACE", 6.6),
        (100, "ALT", 1.0), (97, "CTRL", 1.0),
        (105, "←", 1.0), (108, "↓", 1.0), (106, "→", 1.0)
    ]
]


class KeyboardPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(170)
        self.key_counts: Dict[int, int] = {}
        self.hover_code = None
        self.setMouseTracking(True)
        self.key_rects = []
        self.setAccessibleName("Keyboard heatmap of key presses")

    def set_data(self, key_counts: Dict[int, int]):
        self.key_counts = key_counts
        top = sorted(key_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
        names = {code: lbl for row in KEYBOARD_ROWS for code, lbl, _ in row}
        self.setAccessibleDescription(", ".join(f"{names.get(c, c)} {n}" for c, n in top) or "No key presses")
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        total_keys = sum(self.key_counts.values())
        for rect, code, label, count in self.key_rects:
            if rect.contains(pos):
                if code != self.hover_code:
                    self.hover_code = code
                    self.update()
                pct = round((count / total_keys * 100), 1) if total_keys > 0 else 0.0
                QToolTip.showText(event.globalPosition().toPoint(), f"{label}\n{format_number(count)} presses  ·  {pct}%", self)
                return
        if self.hover_code is not None:
            self.hover_code = None
            self.update()
        QToolTip.hideText()

    def leaveEvent(self, event):
        self.hover_code = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.key_rects = []
        w = float(self.width())
        h = float(self.height())

        total_units = 14.8
        row_count = 5.0
        gap = max(3.0, min(5.0, w / 180.0))

        avail_w = max(100.0, w - 8.0)
        avail_h = max(80.0, h - 8.0)

        unit_w = max(4.0, (avail_w - (total_units * gap)) / total_units)
        unit_h = max(10.0, (avail_h - (row_count * gap)) / row_count)

        # Preserve natural key proportions (aspect ratio ~1:1) when stretched horizontally or vertically
        target_unit = max(8.0, min(unit_w, unit_h * 1.25))
        key_unit_w = target_unit
        key_h = max(14.0, min(unit_h, target_unit * 0.95))

        total_kb_w = total_units * key_unit_w + (total_units - 1.0) * gap
        total_kb_h = row_count * key_h + (row_count - 1.0) * gap

        x_start = max(4.0, (w - total_kb_w) / 2.0)
        y_start = max(4.0, (h - total_kb_h) / 2.0)

        max_count = max(self.key_counts.values()) if self.key_counts else 1
        if max_count == 0:
            max_count = 1

        f_size = max(9, min(13, int(key_h * 0.34)))
        font_used, font_unused = t.font(f_size, QFont.Weight.DemiBold), t.font(f_size, QFont.Weight.Medium)
        for r_idx, row in enumerate(KEYBOARD_ROWS):
            x_cursor = x_start
            y_pos = y_start + r_idx * (key_h + gap)

            for code, label, width_u in row:
                key_w = width_u * key_unit_w + (width_u - 1.0) * gap
                rect = QRectF(x_cursor, y_pos, key_w, key_h)
                count = self.key_counts.get(code, 0)
                self.key_rects.append((rect, code, label, count))

                # sqrt scale: one dominant key (space) shouldn't flatten everything else
                ratio = math.sqrt(count / float(max_count)) if count else 0.0
                bg = t.heat(t.SERIES_KEYS, ratio)
                painter.setBrush(bg)
                if code == self.hover_code:
                    painter.setPen(QPen(QColor(t.TEXT), 1.5))
                elif count == 0:
                    painter.setPen(QPen(QColor(t.BORDER), 1.0))
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)

                painter.setPen(QColor(t.TEXT_3) if count == 0 else t.ink_on(bg))
                painter.setFont(font_used if count else font_unused)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

                x_cursor += key_w + gap

        painter.end()


class KeyboardHeatmapWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.PAD, t.PAD, t.PAD, 14)
        lay.setSpacing(10)

        hdr, _, self.sub_lbl = card_header("Keyboard", "Key presses")
        lay.addLayout(hdr)

        self.keyboard_painter = KeyboardPainter(self)
        lay.addWidget(self.keyboard_painter, 1)

        foot = QHBoxLayout()
        self.total_lbl = t.label("", "caption")
        foot.addWidget(self.total_lbl)
        foot.addStretch()
        foot.addWidget(RampLegend(t.SERIES_KEYS))
        lay.addLayout(foot)

    def update_data(self, key_counts: Dict[int, int], range_type: str = "day"):
        total = sum(key_counts.values())
        self.total_lbl.setText(f"{format_number(total)} key presses" if total else "No key presses in this range")
        self.keyboard_painter.set_data(key_counts)

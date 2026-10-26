import math
from typing import Dict
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QToolTip, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QPainterPath
from .. import theme as t
from ..utils import format_number
from .common import RampLegend, card_header

BUTTON_NAMES = {
    "left": "Left click",
    "right": "Right click",
    "middle": "Middle click (wheel)",
    "side1": "Side button (back)",
    "side2": "Side button (forward)",
}


class MousePainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(170)
        self.mouse_counts: Dict[str, int] = {}
        self.hover = ""
        self.setMouseTracking(True)
        self.btn_rects = []
        self.setAccessibleName("Mouse button heatmap")

    def set_data(self, mouse_counts: Dict[str, int]):
        self.mouse_counts = mouse_counts
        self.setAccessibleDescription(", ".join(f"{BUTTON_NAMES.get(k, k)} {v}" for k, v in mouse_counts.items()) or "No clicks")
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        total_clicks = sum(self.mouse_counts.values())
        # Smallest targets first so the wheel wins over the button underneath it
        for rect, name, label, count in sorted(self.btn_rects, key=lambda b: b[0].width() * b[0].height()):
            if rect.adjusted(-3, -3, 3, 3).contains(pos):
                if name != self.hover:
                    self.hover = name
                    self.update()
                pct = round((count / total_clicks * 100), 1) if total_clicks > 0 else 0.0
                QToolTip.showText(event.globalPosition().toPoint(), f"{label}\n{format_number(count)} clicks  ·  {pct}%", self)
                return
        if self.hover:
            self.hover = ""
            self.update()
        QToolTip.hideText()

    def leaveEvent(self, event):
        self.hover = ""
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.btn_rects = []
        w = float(self.width())
        h = float(self.height())

        avail_w = max(40.0, w - 24.0)
        avail_h = max(60.0, h - 8.0)
        mh = max(60.0, min(240.0, min(avail_h, avail_w * 1.5)))
        mw = mh / 1.5
        mx = (w - mw) / 2.0
        my = (h - mh) / 2.0

        max_count = max(self.mouse_counts.values()) if self.mouse_counts else 1
        if max_count == 0:
            max_count = 1

        def paint_button(rect: QRectF, name: str, radius: float, caption: str = ""):
            count = self.mouse_counts.get(name, 0)
            self.btn_rects.append((rect, name, BUTTON_NAMES[name], count))
            bg = t.heat(t.SERIES_CLICKS, math.sqrt(count / float(max_count)) if count else 0.0)
            painter.setBrush(bg)
            painter.setPen(QPen(QColor(t.TEXT if name == self.hover else t.BORDER_STRONG), 1.5 if name == self.hover else 1.0))
            painter.drawRoundedRect(rect, radius, radius)
            if caption:
                painter.setPen(QColor(t.TEXT_3) if count == 0 else t.ink_on(bg))
                painter.setFont(t.font(max(10, int(mw * 0.075)), QFont.Weight.DemiBold))
                painter.drawText(rect.adjusted(0, rect.height() * 0.35, 0, 0), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                                 f"{caption}\n{format_number(count)}")

        # Body
        body = QPainterPath()
        body.addRoundedRect(QRectF(mx, my, mw, mh), mw * 0.42, mw * 0.42)
        painter.setBrush(QColor(t.RAISED))
        painter.setPen(QPen(QColor(t.BORDER_STRONG), 1.2))
        painter.drawPath(body)

        btn_w = (mw / 2.0) - 6.0
        btn_h = mh * 0.44
        paint_button(QRectF(mx + 4, my + 4, btn_w, btn_h), "left", mw * 0.3, "L")
        paint_button(QRectF(mx + mw / 2.0 + 2, my + 4, btn_w, btn_h), "right", mw * 0.3, "R")

        wheel_w, wheel_h = mw * 0.13, mh * 0.17
        paint_button(QRectF(mx + (mw - wheel_w) / 2.0, my + mh * 0.11, wheel_w, wheel_h), "middle", wheel_w / 2)
        paint_button(QRectF(mx - 6, my + mh * 0.34, 6, mh * 0.13), "side1", 3)
        paint_button(QRectF(mx - 6, my + mh * 0.50, 6, mh * 0.13), "side2", 3)

        painter.end()


class MouseHeatmapWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.PAD, t.PAD, t.PAD, 14)
        lay.setSpacing(10)

        hdr, _, self.sub_lbl = card_header("Mouse", "Clicks")
        lay.addLayout(hdr)

        self.mouse_painter = MousePainter(self)
        lay.addWidget(self.mouse_painter, 1)

        foot = QHBoxLayout()
        self.total_lbl = t.label("", "caption")
        foot.addWidget(self.total_lbl)
        foot.addStretch()
        foot.addWidget(RampLegend(t.SERIES_CLICKS))
        lay.addLayout(foot)

    def update_data(self, mouse_counts: Dict[str, int], range_type: str = "day"):
        total = sum(mouse_counts.values())
        self.total_lbl.setText(f"{format_number(total)} clicks" if total else "No clicks yet")
        self.mouse_painter.set_data(mouse_counts)

from typing import Dict, Any
from PyQt6.QtCore import Qt, QRectF, QPoint
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolTip, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPainterPath
from ..utils import format_number

class MousePainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.mouse_counts: Dict[str, int] = {}
        self.setMouseTracking(True)
        self.btn_rects = []

    def set_data(self, mouse_counts: Dict[str, int]):
        self.mouse_counts = mouse_counts
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        total_clicks = sum(self.mouse_counts.values())
        for rect, name, label, count in self.btn_rects:
            if rect.contains(pos.x(), pos.y()):
                pct = round((count / total_clicks * 100), 1) if total_clicks > 0 else 0.0
                tip = f"🖱 {label}\nClicks: {format_number(count)} ({pct}%)"
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.btn_rects = []
        w = float(self.width())
        h = float(self.height())

        # Scale mouse body dynamically to fit widget
        mh = max(130.0, min(h - 16.0, (w - 24.0) * 1.5))
        mw = mh / 1.5
        mx = (w - mw) / 2.0
        my = (h - mh) / 2.0

        max_count = max(self.mouse_counts.values()) if self.mouse_counts else 1
        if max_count == 0:
            max_count = 1

        def get_btn_color(btn_name):
            cnt = self.mouse_counts.get(btn_name, 0)
            if cnt == 0:
                return QColor("#111827"), QColor("#1f293d"), QColor("#64748b"), cnt
            ratio = cnt / float(max_count)
            if ratio < 0.20:
                return QColor("#064e3b"), QColor("#047857"), QColor("#a7f3d0"), cnt
            elif ratio < 0.50:
                return QColor("#047857"), QColor("#10b981"), QColor("#ffffff"), cnt
            elif ratio < 0.80:
                return QColor("#059669"), QColor("#34d399"), QColor("#ffffff"), cnt
            else:
                return QColor("#10b981"), QColor("#6ee7b7"), QColor("#ffffff"), cnt

        # 1. Mouse Body
        body_path = QPainterPath()
        body_rect = QRectF(mx, my, mw, mh)
        body_path.addRoundedRect(body_rect, mw * 0.32, mw * 0.32)
        painter.setBrush(QBrush(QColor("#0b101b")))
        painter.setPen(QPen(QColor("#1e293b"), 1.8))
        painter.drawPath(body_path)

        # 2. Left Button (LMB)
        btn_w = (mw / 2.0) - 7.0
        btn_h = mh * 0.44
        left_rect = QRectF(mx + 5, my + 5, btn_w, btn_h)
        bg, border, text_c, count = get_btn_color("left")
        self.btn_rects.append((left_rect, "left", "Left Click", count))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1.4))
        painter.drawRoundedRect(left_rect, 12, 12)
        painter.setPen(text_c)
        painter.setFont(QFont("Inter", max(7, int(mw * 0.07)), QFont.Weight.Bold))
        painter.drawText(left_rect, Qt.AlignmentFlag.AlignCenter, f"LMB\n{format_number(count)}")

        # 3. Right Button (RMB)
        right_rect = QRectF(mx + (mw / 2.0) + 2, my + 5, btn_w, btn_h)
        bg, border, text_c, count = get_btn_color("right")
        self.btn_rects.append((right_rect, "right", "Right Click", count))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1.4))
        painter.drawRoundedRect(right_rect, 12, 12)
        painter.setPen(text_c)
        painter.setFont(QFont("Inter", max(7, int(mw * 0.07)), QFont.Weight.Bold))
        painter.drawText(right_rect, Qt.AlignmentFlag.AlignCenter, f"RMB\n{format_number(count)}")

        # 4. Scroll Wheel / Middle Button
        wheel_w = mw * 0.14
        wheel_h = mh * 0.18
        wheel_rect = QRectF(mx + (mw - wheel_w) / 2.0, my + mh * 0.12, wheel_w, wheel_h)
        bg, border, text_c, count = get_btn_color("middle")
        self.btn_rects.append((wheel_rect, "middle", "Middle Click (Wheel)", count))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1.4))
        painter.drawRoundedRect(wheel_rect, 6, 6)

        # 5. Side Buttons (Back / Forward)
        side1_rect = QRectF(mx - 7, my + mh * 0.32, 7, mh * 0.14)
        bg, border, text_c, count = get_btn_color("side1")
        self.btn_rects.append((side1_rect, "side1", "Side Button (Back)", count))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(side1_rect, 2.5, 2.5)

        side2_rect = QRectF(mx - 7, my + mh * 0.48, 7, mh * 0.14)
        bg, border, text_c, count = get_btn_color("side2")
        self.btn_rects.append((side2_rect, "side2", "Side Button (Forward)", count))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(side2_rect, 2.5, 2.5)

        # 6. Palm Rest Label
        painter.setPen(QColor("#475569"))
        painter.setFont(QFont("Inter", max(7, int(mw * 0.065)), QFont.Weight.Medium))
        painter.drawText(QRectF(mx, my + mh * 0.68, mw, 18), Qt.AlignmentFlag.AlignCenter, "MOUSE CLICKS")

        painter.end()


class MouseHeatmapWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("PHYSICAL MOUSE HEATMAP")
        title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        sub = QLabel("Clicks")
        sub.setStyleSheet("font-size: 10px; color: #64748b; font-family: monospace;")
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(sub)
        lay.addLayout(hdr)

        self.mouse_painter = MousePainter(self)
        lay.addWidget(self.mouse_painter, 1)

    def update_data(self, mouse_counts: Dict[str, int]):
        self.mouse_painter.set_data(mouse_counts)

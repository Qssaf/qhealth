from typing import List, Dict, Any
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolTip, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush
from ..utils import format_duration, format_number

HEATMAP_COLORS = [
    QColor("#131a29"),
    QColor("#064e3b"),
    QColor("#047857"),
    QColor("#0e7490"),
    QColor("#38bdf8"),
]

class HeatmapPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(110)
        self.heatmap_data: List[Dict[str, Any]] = []
        self.setMouseTracking(True)
        self.cell_rects = []

    def set_data(self, data: List[Dict[str, Any]]):
        self.heatmap_data = data
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        for rect, d in self.cell_rects:
            if rect.contains(pos.x(), pos.y()):
                tip = (
                    f"📅 {d['date']} ({d['day_name']})\n"
                    f"⏱ Active: {format_duration(d['duration'])}\n"
                    f"⌨ Keys: {format_number(d['keystrokes'])} · 🖱 Clicks: {format_number(d['clicks'])}"
                )
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.cell_rects = []
        if not self.heatmap_data:
            painter.end()
            return

        w = float(self.width())
        h = float(self.height())

        first_item = self.heatmap_data[0]
        start_weekday = first_item.get("weekday", 0)

        # Calculate number of week columns
        total_days = len(self.heatmap_data)
        num_cols = max(1, (total_days + start_weekday + 6) // 7)

        left_pad = 30.0
        top_pad = 12.0
        gap = 3.5

        # Compute dynamic cell size to fill width & height
        avail_w = w - left_pad - 16.0
        avail_h = h - top_pad - 22.0

        cell_w = (avail_w - (num_cols * gap)) / float(num_cols)
        cell_h = (avail_h - (7.0 * gap)) / 7.0
        cell_size = max(8.0, min(14.0, min(cell_w, cell_h)))

        # Day of week labels on left (Mon, Wed, Fri)
        painter.setPen(QColor("#64748b"))
        font = QFont("Inter", 8)
        painter.setFont(font)
        painter.drawText(QRectF(0, top_pad + 0 * (cell_size + gap), 24, cell_size), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Mon")
        painter.drawText(QRectF(0, top_pad + 2 * (cell_size + gap), 24, cell_size), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Wed")
        painter.drawText(QRectF(0, top_pad + 4 * (cell_size + gap), 24, cell_size), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Fri")

        col = 0
        row = start_weekday

        for d in self.heatmap_data:
            x = left_pad + col * (cell_size + gap)
            y = top_pad + row * (cell_size + gap)

            rect = QRectF(x, y, cell_size, cell_size)
            self.cell_rects.append((rect, d))

            lvl = min(4, max(0, d.get("level", 0)))
            color = HEATMAP_COLORS[lvl]

            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 2.5, 2.5)

            row += 1
            if row > 6:
                row = 0
                col += 1

        # Legend at bottom right
        leg_x = w - 120
        leg_y = h - 14
        painter.drawText(QRectF(leg_x - 30, leg_y - 2, 28, 12), Qt.AlignmentFlag.AlignRight, "Less")
        for i, c in enumerate(HEATMAP_COLORS):
            bx = leg_x + i * 13
            painter.setBrush(QBrush(c))
            painter.drawRoundedRect(QRectF(bx, leg_y, 9, 9), 2, 2)
        painter.drawText(QRectF(leg_x + 5 * 13 + 4, leg_y - 2, 30, 12), Qt.AlignmentFlag.AlignLeft, "More")

        painter.end()


class HeatmapGridWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("DAILY ACTIVITY & INPUT HEATMAP")
        title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        sub = QLabel("Last 10 Weeks")
        sub.setStyleSheet("font-size: 10px; color: #64748b; font-family: monospace;")
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(sub)
        lay.addLayout(hdr)

        self.painter_widget = HeatmapPainter(self)
        lay.addWidget(self.painter_widget, 1)

    def update_data(self, data: List[Dict[str, Any]]):
        self.painter_widget.set_data(data)

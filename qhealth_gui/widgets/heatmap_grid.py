import datetime
from typing import List, Dict, Any
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QToolTip, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QPen
from .. import theme as t
from ..utils import format_duration, format_number
from .common import RampLegend, card_header


class HeatmapPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(150)
        self.heatmap_data: List[Dict[str, Any]] = []
        self.hover = -1
        self.setMouseTracking(True)
        self.cell_rects = []
        self.setAccessibleName("Daily activity calendar, last 10 weeks")

    def set_data(self, data: List[Dict[str, Any]]):
        self.heatmap_data = data
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        for i, (rect, d) in enumerate(self.cell_rects):
            if rect.adjusted(-1.5, -1.5, 1.5, 1.5).contains(pos):
                if i != self.hover:
                    self.hover = i
                    self.update()
                QToolTip.showText(event.globalPosition().toPoint(), (
                    f"{d['day_name']}, {d['date']}\n"
                    f"Active {format_duration(d['duration'])}  ·  "
                    f"{format_number(d['keystrokes'])} keys  ·  {format_number(d['clicks'])} clicks"
                ), self)
                return
        if self.hover != -1:
            self.hover = -1
            self.update()
        QToolTip.hideText()

    def leaveEvent(self, event):
        self.hover = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.cell_rects = []
        if not self.heatmap_data:
            painter.end()
            return

        w = float(self.width())
        h = float(self.height())

        start_weekday = self.heatmap_data[0].get("weekday", 0)
        total_days = len(self.heatmap_data)
        num_cols = max(1, (total_days + start_weekday + 6) // 7)

        left_pad, top_pad, gap = 34.0, 20.0, 4.0
        cell_w = (w - left_pad - 4.0 - (num_cols * gap)) / float(num_cols)
        cell_h = (h - top_pad - 4.0 - (7.0 * gap)) / 7.0
        cell = max(8.0, min(28.0, min(cell_w, cell_h)))
        grid_w = num_cols * (cell + gap)
        x0 = left_pad + max(0.0, (w - left_pad - grid_w) / 2.0)

        painter.setFont(t.font(11))
        painter.setPen(QColor(t.TEXT_3))
        for row, name in ((0, "Mon"), (2, "Wed"), (4, "Fri"), (6, "Sun")):
            painter.drawText(QRectF(x0 - left_pad, top_pad + row * (cell + gap), left_pad - 8, cell),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, name)

        col, row = 0, start_weekday
        last_month, last_label_x = None, -100.0
        for d in self.heatmap_data:
            x = x0 + col * (cell + gap)
            y = top_pad + row * (cell + gap)
            rect = QRectF(x, y, cell, cell)
            self.cell_rects.append((rect, d))

            # Month label above the first column that starts a new month
            try:
                month = datetime.datetime.strptime(d.get("date", ""), "%Y-%m-%d").strftime("%b")
            except ValueError:
                month = None
            if month and month != last_month and (row == 0 or last_month is None):
                if x - last_label_x >= 32:
                    painter.setPen(QColor(t.TEXT_3))
                    painter.drawText(QRectF(x, 0, 40, top_pad - 4), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, month)
                    last_label_x = x
                last_month = month

            lvl = min(4, max(0, d.get("level", 0)))
            painter.setBrush(t.heat(t.SERIES_TIME, lvl / 4.0))
            idx = len(self.cell_rects) - 1
            painter.setPen(QPen(QColor(t.TEXT), 1.5) if idx == self.hover else Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 4, 4)

            row += 1
            if row > 6:
                row = 0
                col += 1

        painter.end()


class HeatmapGridWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.PAD, t.PAD, t.PAD, 14)
        lay.setSpacing(10)

        hdr, _, _ = card_header("Activity calendar", "Last 10 weeks")
        hdr.addWidget(RampLegend(t.SERIES_TIME))
        lay.addLayout(hdr)

        self.painter_widget = HeatmapPainter(self)
        lay.addWidget(self.painter_widget, 1)

    def update_data(self, data: List[Dict[str, Any]]):
        self.painter_widget.set_data(data)

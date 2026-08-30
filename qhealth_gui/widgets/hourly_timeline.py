from typing import List, Dict, Any
from datetime import datetime
from PyQt6.QtCore import Qt, QRectF, QPoint
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolTip, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient
from ..utils import format_duration, format_number

RANGE_TITLES = {
    "day": ("24-HOUR ACTIVITY TIMELINE", "Hourly active time distribution"),
    "week": ("7-DAY ACTIVITY BREAKDOWN", "Daily screen time across past 7 days"),
    "month": ("30-DAY ACTIVITY BREAKDOWN", "Daily screen time across past 30 days"),
    "year": ("MONTHLY ACTIVITY DISTRIBUTION", "Monthly breakdown for this year"),
    "all_time": ("ALL-TIME MONTHLY DISTRIBUTION", "Historical monthly activity")
}

class TimelineBarsPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(130)
        self.timeline_data: List[Dict[str, Any]] = []
        self.range_type = "day"
        self.setMouseTracking(True)
        self.hovered_idx = -1
        self.bar_rects = [] # list of (QRectF, data, label)

    def set_data(self, timeline_data: List[Dict[str, Any]], range_type: str = "day"):
        self.timeline_data = timeline_data
        self.range_type = range_type
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        for rect, d, lbl in self.bar_rects:
            if rect.contains(pos.x(), pos.y()):
                dur = d.get("duration", 0)
                keys = d.get("keystrokes", 0)
                clicks = d.get("clicks", 0)
                tip = f"{lbl}\n⏱ Active: {format_duration(dur)}\n⌨ Keys: {format_number(keys)} · 🖱 Clicks: {format_number(clicks)}"
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hovered_idx = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.bar_rects = []
        w = float(self.width())
        h = float(self.height()) - 22.0

        if not self.timeline_data:
            painter.end()
            return

        count = len(self.timeline_data)
        col_w = w / float(count)
        bar_w = max(3.0, min(36.0, col_w - 4.0))

        max_duration = max([d.get("duration", 0) for d in self.timeline_data] + [1])
        if self.range_type == "day":
            max_duration = max(3600.0, float(max_duration)) # standard 1-hour scale for day

        current_hour = datetime.now().hour
        is_today_view = (self.range_type == "day")

        for i, item in enumerate(self.timeline_data):
            dur = item.get("duration", 0)
            x = i * col_w + (col_w - bar_w) / 2.0
            pct = min(1.0, max(0.04, dur / float(max_duration)))
            bar_h = pct * (h - 10)
            y = h - bar_h

            rect = QRectF(x, y, bar_w, bar_h)

            # Label for tooltip
            if self.range_type == "day":
                h_int = item.get("hour_int", i)
                lbl_text = f"🕒 {h_int:02d}:00"
                is_active_highlight = (h_int == current_hour)
            elif self.range_type in ("week", "month"):
                lbl_text = f"📅 {item.get('date', '')} ({item.get('label', '')})"
                is_active_highlight = (i == count - 1)
            else:
                lbl_text = f"📅 {item.get('month_str', '')}"
                is_active_highlight = (i == count - 1)

            self.bar_rects.append((rect, item, lbl_text))

            # Color gradient
            if is_active_highlight:
                grad = QLinearGradient(x, y, x, h)
                grad.setColorAt(0, QColor("#34d399"))
                grad.setColorAt(1, QColor("#06b6d4"))
                painter.setBrush(QBrush(grad))
            elif dur > 0:
                painter.setBrush(QColor(16, 185, 129, 130))
            else:
                painter.setBrush(QColor(30, 41, 59, 80))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 3.0, 3.0)

        # X-axis labels
        painter.setPen(QColor("#64748b"))
        font = QFont("monospace", 8)
        painter.setFont(font)

        if self.range_type == "day":
            labels = [(0, "00:00"), (4, "04:00"), (8, "08:00"), (12, "12:00"), (16, "16:00"), (20, "20:00"), (23, "23:00")]
            for hour, txt in labels:
                lx = hour * col_w
                painter.drawText(QRectF(lx - 10, h + 4, 40, 16), Qt.AlignmentFlag.AlignCenter, txt)
        elif self.range_type == "week":
            for i, item in enumerate(self.timeline_data):
                lx = i * col_w
                painter.drawText(QRectF(lx - 6, h + 4, col_w + 12, 16), Qt.AlignmentFlag.AlignCenter, item.get("label", ""))
        elif self.range_type == "month":
            # Draw every 5 days
            for i, item in enumerate(self.timeline_data):
                if i % 5 == 0 or i == count - 1:
                    lx = i * col_w
                    d_str = item.get("date", "")[-2:]
                    painter.drawText(QRectF(lx - 10, h + 4, 30, 16), Qt.AlignmentFlag.AlignCenter, d_str)
        else:
            for i, item in enumerate(self.timeline_data):
                lx = i * col_w
                m_label = item.get("label", item.get("month_str", "")[-2:])
                painter.drawText(QRectF(lx - 10, h + 4, col_w + 20, 16), Qt.AlignmentFlag.AlignCenter, m_label)

        painter.end()


class HourlyTimelineWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        self.title_lbl = QLabel("24-HOUR ACTIVITY TIMELINE")
        self.title_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        self.sub_lbl = QLabel("Hover bar for details")
        self.sub_lbl.setStyleSheet("font-size: 10px; color: #64748b; font-family: monospace;")
        hdr.addWidget(self.title_lbl)
        hdr.addStretch()
        hdr.addWidget(self.sub_lbl)
        lay.addLayout(hdr)

        self.painter_widget = TimelineBarsPainter(self)
        lay.addWidget(self.painter_widget)

    def update_data(self, timeline_data: List[Dict[str, Any]], range_type: str = "day"):
        t_title, t_sub = RANGE_TITLES.get(range_type, ("ACTIVITY TIMELINE", "Activity breakdown"))
        self.title_lbl.setText(t_title)
        self.sub_lbl.setText(t_sub)
        self.painter_widget.set_data(timeline_data, range_type)

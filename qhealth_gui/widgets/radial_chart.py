import math
from typing import List, Dict, Any
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QBrush
from ..utils import format_duration, get_app_color, get_app_icon_pixmap

class RadialRingPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.total_seconds = 0
        self.apps: List[Dict[str, Any]] = []

    def set_data(self, total_seconds: int, apps: List[Dict[str, Any]]):
        self.total_seconds = total_seconds
        self.apps = apps
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        size = min(w, h) - 24
        x = (w - size) / 2
        y = (h - size) / 2
        rect = QRectF(x, y, size, size)

        stroke_width = 16.0

        # Background track
        track_pen = QPen(QColor(30, 41, 59, 150), stroke_width)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        # Draw Top Applications segments
        if self.total_seconds > 0 and self.apps:
            start_angle = 90 * 16 # Start from top (90 deg in 1/16th deg units)
            for idx, app in enumerate(self.apps[:5]):
                dur = app.get("duration", 0)
                if dur <= 0:
                    continue
                span = -int((dur / self.total_seconds) * 360 * 16)
                app_color = get_app_color(app.get("app_name", ""), idx)

                pen = QPen(app_color, stroke_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawArc(rect, start_angle, span)

                start_angle += span

        # Center typography
        painter.setPen(QColor("#f8fafc"))
        font = QFont("Inter", 18, QFont.Weight.Bold)
        painter.setFont(font)

        dur_text = format_duration(self.total_seconds)
        text_rect = QRectF(x, y + size * 0.32, size, size * 0.22)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, dur_text)

        painter.setPen(QColor("#94a3b8"))
        sub_font = QFont("Inter", 9, QFont.Weight.Medium)
        painter.setFont(sub_font)
        sub_rect = QRectF(x, y + size * 0.54, size, size * 0.16)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, "Total Active")

        painter.end()


class RadialChartWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setObjectName("RadialCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("TOP APPLICATIONS BREAKDOWN")
        title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        self.tag_lbl = QLabel("Today")
        self.tag_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #34d399; background-color: rgba(16,185,129,0.15); padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(16,185,129,0.3);")
        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(self.tag_lbl)
        layout.addLayout(hdr)

        # Main content (Radial Ring + Top Apps Legend)
        content = QHBoxLayout()
        content.setSpacing(16)

        self.ring_painter = RadialRingPainter(self)
        content.addWidget(self.ring_painter, alignment=Qt.AlignmentFlag.AlignCenter)

        # Legend list
        self.legend_layout = QVBoxLayout()
        self.legend_layout.setSpacing(6)
        self.legend_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        content.addLayout(self.legend_layout)

        layout.addLayout(content)

    def update_data(self, total_seconds: int, apps: List[Dict[str, Any]], range_type: str = "day"):
        self.ring_painter.set_data(total_seconds, apps)

        range_tags = {
            "day": "Today",
            "week": "Last 7 Days",
            "month": "Last 30 Days",
            "year": "This Year",
            "all_time": "All Time"
        }
        self.tag_lbl.setText(range_tags.get(range_type, "Custom"))

        # Clear legend
        while self.legend_layout.count():
            item = self.legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not apps:
            empty_lbl = QLabel("No active apps in range")
            empty_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-style: italic;")
            self.legend_layout.addWidget(empty_lbl)
            return

        # Add top 5 applications
        for idx, app in enumerate(apps[:5]):
            app_name = app.get("app_name", "Unknown")
            app_id = app.get("app_id", "")
            icon_name = app.get("icon", app_id)
            dur = app.get("duration", 0)
            pct = app.get("percentage", 0)
            color = get_app_color(app_name, idx)

            row = QFrame()
            row.setProperty("class", "GlassCardInner")
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(10, 6, 10, 6)
            r_lay.setSpacing(8)

            # App icon
            icon_lbl = QLabel()
            icon_lbl.setFixedSize(20, 20)
            icon_lbl.setPixmap(get_app_icon_pixmap(icon_name, app_name, 20))

            name_lbl = QLabel(app_name)
            name_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #ffffff;")

            dur_lbl = QLabel(f"{format_duration(dur)} ({pct}%)")
            dur_lbl.setStyleSheet("font-size: 11px; color: #34d399; font-family: monospace; font-weight: 600;")

            r_lay.addWidget(icon_lbl)
            r_lay.addWidget(name_lbl)
            r_lay.addStretch()
            r_lay.addWidget(dur_lbl)

            self.legend_layout.addWidget(row)

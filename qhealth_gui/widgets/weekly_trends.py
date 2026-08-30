from typing import List, Dict, Any
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush, QLinearGradient
from ..utils import format_duration, format_number

class WeekBarsPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.days: List[Dict[str, Any]] = []

    def set_data(self, days: List[Dict[str, Any]]):
        self.days = days
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height() - 36

        if not self.days:
            painter.end()
            return

        max_dur = max([d.get("total_duration", 0) for d in self.days] + [1])
        count = len(self.days)
        col_w = w / float(count)
        bar_w = min(46.0, col_w - 14.0)

        for i, d in enumerate(self.days):
            dur = d.get("total_duration", 0)
            day_name = d.get("day_name", "")
            date_str = d.get("date", "")
            is_today = (i == count - 1)

            pct = max(0.06, dur / float(max_dur))
            bar_h = pct * (h - 24)
            x = i * col_w + (col_w - bar_w) / 2.0
            y = h - bar_h

            rect = QRectF(x, y, bar_w, bar_h)

            # Paint Bar
            if dur > 0 and is_today:
                grad = QLinearGradient(x, y, x, h)
                grad.setColorAt(0, QColor("#34d399"))
                grad.setColorAt(1, QColor("#06b6d4"))
                painter.setBrush(QBrush(grad))
                painter.setPen(Qt.PenStyle.NoPen)
            elif dur > 0:
                painter.setBrush(QColor(16, 185, 129, 140))
                painter.setPen(Qt.PenStyle.NoPen)
            else:
                painter.setBrush(QColor(30, 41, 59, 80))
                painter.setPen(Qt.PenStyle.NoPen)

            painter.drawRoundedRect(rect, 6, 6)

            # Draw duration above bar
            painter.setPen(QColor("#34d399" if is_today else "#94a3b8"))
            font_dur = QFont("monospace", 8, QFont.Weight.Bold if is_today else QFont.Weight.Normal)
            painter.setFont(font_dur)
            painter.drawText(QRectF(x - 10, y - 18, bar_w + 20, 16), Qt.AlignmentFlag.AlignCenter, format_duration(dur))

            # Day label below bar
            painter.setPen(QColor("#f8fafc" if is_today else "#64748b"))
            font_day = QFont("Inter", 9, QFont.Weight.Bold if is_today else QFont.Weight.Normal)
            painter.setFont(font_day)
            painter.drawText(QRectF(x - 10, h + 4, bar_w + 20, 16), Qt.AlignmentFlag.AlignCenter, day_name)

            # Date snippet
            painter.setPen(QColor("#475569"))
            font_date = QFont("monospace", 7)
            painter.setFont(font_date)
            painter.drawText(QRectF(x - 10, h + 20, bar_w + 20, 14), Qt.AlignmentFlag.AlignCenter, date_str[-5:])

        painter.end()


class WeeklyTrendsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(14)

        # 3 Overview Cards
        cards_lay = QHBoxLayout()
        cards_lay.setSpacing(12)

        self.card_total = QFrame()
        self.card_total.setProperty("class", "GlassCard")
        c1 = QVBoxLayout(self.card_total)
        c1.setContentsMargins(16, 12, 16, 12)
        c1.setSpacing(4)
        c1.addWidget(QLabel("7-DAY TOTAL SCREEN TIME"))
        self.val_total = QLabel("0h 0m")
        self.val_total.setStyleSheet("font-size: 20px; font-weight: 800; color: #34d399; font-family: monospace;")
        self.sub_total = QLabel("~0h 0m / day avg")
        self.sub_total.setStyleSheet("font-size: 10px; color: #64748b;")
        c1.addWidget(self.val_total)
        c1.addWidget(self.sub_total)
        cards_lay.addWidget(self.card_total)

        self.card_keys = QFrame()
        self.card_keys.setProperty("class", "GlassCard")
        c2 = QVBoxLayout(self.card_keys)
        c2.setContentsMargins(16, 12, 16, 12)
        c2.setSpacing(4)
        c2.addWidget(QLabel("7-DAY KEYSTROKES"))
        self.val_keys = QLabel("0")
        self.val_keys.setStyleSheet("font-size: 20px; font-weight: 800; color: #22d3ee; font-family: monospace;")
        c2.addWidget(self.val_keys)
        c2.addWidget(QLabel("Total keyboard activity"))
        cards_lay.addWidget(self.card_keys)

        self.card_clicks = QFrame()
        self.card_clicks.setProperty("class", "GlassCard")
        c3 = QVBoxLayout(self.card_clicks)
        c3.setContentsMargins(16, 12, 16, 12)
        c3.setSpacing(4)
        c3.addWidget(QLabel("7-DAY MOUSE CLICKS"))
        self.val_clicks = QLabel("0")
        self.val_clicks.setStyleSheet("font-size: 20px; font-weight: 800; color: #818cf8; font-family: monospace;")
        c3.addWidget(self.val_clicks)
        c3.addWidget(QLabel("Total mouse actions"))
        cards_lay.addWidget(self.card_clicks)

        main_lay.addLayout(cards_lay)

        # Bar chart card
        chart_card = QFrame()
        chart_card.setProperty("class", "GlassCard")
        c_lay = QVBoxLayout(chart_card)
        c_lay.setContentsMargins(18, 16, 18, 16)
        c_lay.setSpacing(10)

        t_lbl = QLabel("DAILY SCREEN TIME CONSISTENCY")
        t_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        c_lay.addWidget(t_lbl)

        self.bars = WeekBarsPainter(chart_card)
        c_lay.addWidget(self.bars)

        main_lay.addWidget(chart_card)

    def update_data(self, days: List[Dict[str, Any]]):
        self.bars.set_data(days)

        total_dur = sum(d.get("total_duration", 0) for d in days)
        avg_dur = total_dur // max(1, len(days))
        total_keys = sum(d.get("total_keystrokes", 0) for d in days)
        total_clicks = sum(d.get("total_clicks", 0) for d in days)

        self.val_total.setText(format_duration(total_dur))
        self.sub_total.setText(f"~{format_duration(avg_dur)} / day average")
        self.val_keys.setText(format_number(total_keys))
        self.val_clicks.setText(format_number(total_clicks))

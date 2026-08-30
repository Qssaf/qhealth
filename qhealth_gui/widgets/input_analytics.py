from typing import List, Dict, Any
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QSizePolicy
)
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush, QLinearGradient
from ..utils import format_number, format_duration
from .heatmap_grid import HeatmapGridWidget
from .keyboard_heatmap import KeyboardHeatmapWidget
from .mouse_heatmap import MouseHeatmapWidget

class HourlyInputBarsPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(110)
        self.hourly = []

    def set_data(self, hourly):
        self.hourly = hourly
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height()) - 20.0

        if not self.hourly:
            painter.end()
            return

        max_val = max([item.get("keystrokes", 0) + item.get("clicks", 0) for item in self.hourly] + [1])
        col_w = w / 24.0
        bar_w = max(4.0, col_w - 4.0)

        for i in range(24):
            item = next((x for x in self.hourly if x.get("hour_int") == i), None)
            keys = item.get("keystrokes", 0) if item else 0
            clicks = item.get("clicks", 0) if item else 0
            total = keys + clicks

            x = i * col_w + (col_w - bar_w) / 2.0
            pct = min(1.0, max(0.04, total / float(max_val)))
            bar_h = pct * (h - 10)
            y = h - bar_h

            rect = QRectF(x, y, bar_w, bar_h)

            if total > 0:
                grad = QLinearGradient(x, y, x, h)
                grad.setColorAt(0, QColor("#22d3ee"))
                grad.setColorAt(1, QColor("#818cf8"))
                painter.setBrush(QBrush(grad))
            else:
                painter.setBrush(QColor(30, 41, 59, 80))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 3, 3)

        # X-axis labels
        painter.setPen(QColor("#64748b"))
        font = QFont("monospace", 8)
        painter.setFont(font)
        labels = [(0, "00:00"), (4, "04:00"), (8, "08:00"), (12, "12:00"), (16, "16:00"), (20, "20:00"), (23, "23:00")]
        for hour, txt in labels:
            lx = hour * col_w
            painter.drawText(QRectF(lx - 10, h + 4, 40, 16), Qt.AlignmentFlag.AlignCenter, txt)

        painter.end()


class InputAnalyticsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(12)

        # 1. Top Stat Cards (Compact single row)
        cards_lay = QHBoxLayout()
        cards_lay.setSpacing(12)

        self.card_keys = QFrame()
        self.card_keys.setProperty("class", "GlassCard")
        k_lay = QVBoxLayout(self.card_keys)
        k_lay.setContentsMargins(14, 10, 14, 10)
        k_lay.setSpacing(2)
        k_lbl = QLabel("TOTAL KEYSTROKES")
        k_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        k_lay.addWidget(k_lbl)
        self.val_keys = QLabel("0")
        self.val_keys.setStyleSheet("font-size: 20px; font-weight: 800; color: #34d399; font-family: monospace;")
        k_lay.addWidget(self.val_keys)
        cards_lay.addWidget(self.card_keys)

        self.card_clicks = QFrame()
        self.card_clicks.setProperty("class", "GlassCard")
        c_lay = QVBoxLayout(self.card_clicks)
        c_lay.setContentsMargins(14, 10, 14, 10)
        c_lay.setSpacing(2)
        c_lbl = QLabel("TOTAL CLICKS")
        c_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        c_lay.addWidget(c_lbl)
        self.val_clicks = QLabel("0")
        self.val_clicks.setStyleSheet("font-size: 20px; font-weight: 800; color: #22d3ee; font-family: monospace;")
        c_lay.addWidget(self.val_clicks)
        cards_lay.addWidget(self.card_clicks)

        self.card_scrolls = QFrame()
        self.card_scrolls.setProperty("class", "GlassCard")
        s_lay = QVBoxLayout(self.card_scrolls)
        s_lay.setContentsMargins(14, 10, 14, 10)
        s_lay.setSpacing(2)
        s_lbl = QLabel("TOTAL SCROLLS")
        s_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        s_lay.addWidget(s_lbl)
        self.val_scrolls = QLabel("0")
        self.val_scrolls.setStyleSheet("font-size: 20px; font-weight: 800; color: #818cf8; font-family: monospace;")
        s_lay.addWidget(self.val_scrolls)
        cards_lay.addWidget(self.card_scrolls)

        main_lay.addLayout(cards_lay)

        # 2. View Toggle Bar (Hardware Heatmaps vs Activity History)
        toggle_bar = QHBoxLayout()
        toggle_bar.setSpacing(8)

        toggle_frame = QFrame()
        toggle_frame.setProperty("class", "GlassCardInner")
        t_lay = QHBoxLayout(toggle_frame)
        t_lay.setContentsMargins(3, 2, 3, 2)
        t_lay.setSpacing(4)

        self.btn_view_hardware = QPushButton("⌨️ Keyboard & Mouse Heatmaps")
        self.btn_view_hardware.setProperty("class", "TabBtn")
        self.btn_view_hardware.setCheckable(True)
        self.btn_view_hardware.setChecked(True)
        self.btn_view_hardware.clicked.connect(lambda: self._switch_view(0))

        self.btn_view_calendar = QPushButton("📅 70-Day Matrix & Hourly")
        self.btn_view_calendar.setProperty("class", "TabBtn")
        self.btn_view_calendar.setCheckable(True)
        self.btn_view_calendar.clicked.connect(lambda: self._switch_view(1))

        t_lay.addWidget(self.btn_view_hardware)
        t_lay.addWidget(self.btn_view_calendar)

        toggle_bar.addWidget(toggle_frame)
        toggle_bar.addStretch()
        main_lay.addLayout(toggle_bar)

        # 3. Stacked View Area (Fills remaining window space with zero scrollbars)
        self.view_stack = QStackedWidget()
        self.view_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # --- VIEW 0: Physical Hardware Heatmaps (Keyboard & Mouse) ---
        page_hw = QWidget()
        page_hw.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        hw_lay = QHBoxLayout(page_hw)
        hw_lay.setContentsMargins(0, 0, 0, 0)
        hw_lay.setSpacing(12)

        self.keyboard_widget = KeyboardHeatmapWidget(page_hw)
        self.mouse_widget = MouseHeatmapWidget(page_hw)

        hw_lay.addWidget(self.keyboard_widget, 72)
        hw_lay.addWidget(self.mouse_widget, 28)

        self.view_stack.addWidget(page_hw)

        # --- VIEW 1: Activity Matrix & Hourly Chart ---
        page_cal = QWidget()
        page_cal.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        cal_lay = QVBoxLayout(page_cal)
        cal_lay.setContentsMargins(0, 0, 0, 0)
        cal_lay.setSpacing(12)

        self.heatmap_calendar = HeatmapGridWidget(page_cal)
        cal_lay.addWidget(self.heatmap_calendar, 5)

        chart_card = QFrame()
        chart_card.setProperty("class", "GlassCard")
        chart_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        ch_lay = QVBoxLayout(chart_card)
        ch_lay.setContentsMargins(14, 12, 14, 12)
        ch_lay.setSpacing(6)
        ch_title = QLabel("HOURLY INPUT ACTIVITY DISTRIBUTION")
        ch_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        ch_lay.addWidget(ch_title)
        self.input_bars = HourlyInputBarsPainter(chart_card)
        ch_lay.addWidget(self.input_bars, 1)
        cal_lay.addWidget(chart_card, 5)

        self.view_stack.addWidget(page_cal)

        main_lay.addWidget(self.view_stack, 1)

    def _switch_view(self, index: int):
        self.view_stack.setCurrentIndex(index)
        self.btn_view_hardware.setChecked(index == 0)
        self.btn_view_calendar.setChecked(index == 1)

    def update_data(
        self,
        keys: int,
        clicks: int,
        scrolls: int,
        key_heatmap: Dict[int, int],
        mouse_heatmap: Dict[str, int],
        calendar_heatmap: List[Dict[str, Any]],
        hourly: List[Dict[str, Any]]
    ):
        self.val_keys.setText(format_number(keys))
        self.val_clicks.setText(format_number(clicks))
        self.val_scrolls.setText(format_number(scrolls))
        self.keyboard_widget.update_data(key_heatmap)
        self.mouse_widget.update_data(mouse_heatmap)
        self.heatmap_calendar.update_data(calendar_heatmap)
        self.input_bars.set_data(hourly)

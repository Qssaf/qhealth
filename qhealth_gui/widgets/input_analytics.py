from typing import List, Dict, Any, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget, QSizePolicy
from .. import theme as t
from ..utils import format_number
from .bar_chart import BarChart, input_value
from .common import card_header
from .heatmap_grid import HeatmapGridWidget
from .keyboard_heatmap import KeyboardHeatmapWidget
from .mouse_heatmap import MouseHeatmapWidget
from .stat_cards import StatCard

INPUT_TITLES = {
    "day": "Input per hour",
    "week": "Input per day",
    "month": "Input per day",
    "year": "Input per month",
    "all_time": "Input per month",
}


class InputAnalyticsWidget(QWidget):
    view_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(t.GAP)

        # 1. Totals
        cards_lay = QHBoxLayout()
        cards_lay.setSpacing(t.GAP)
        self.card_keys = StatCard("KEYSTROKES", t.SERIES_KEYS)
        self.card_clicks = StatCard("CLICKS", t.SERIES_CLICKS)
        self.card_scrolls = StatCard("SCROLLS", t.SERIES_SCROLLS)
        for card in (self.card_keys, self.card_clicks, self.card_scrolls):
            cards_lay.addWidget(card, 1)
        main_lay.addLayout(cards_lay)

        # 2. View switch
        toggle_bar = QHBoxLayout()
        toggle_frame = QFrame()
        toggle_frame.setProperty("class", "Segmented")
        t_lay = QHBoxLayout(toggle_frame)
        t_lay.setContentsMargins(3, 3, 3, 3)
        t_lay.setSpacing(2)

        self.btn_view_hardware = QPushButton("Keyboard && mouse")
        self.btn_view_calendar = QPushButton("Activity calendar")
        for i, btn in enumerate((self.btn_view_hardware, self.btn_view_calendar)):
            btn.setProperty("class", "Segment")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, idx=i: self._switch_view(idx))
            t_lay.addWidget(btn)
        self.btn_view_hardware.setChecked(True)

        toggle_bar.addWidget(toggle_frame)
        toggle_bar.addStretch()
        main_lay.addLayout(toggle_bar)

        # 3. Views
        self.view_stack = QStackedWidget()
        self.view_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        page_hw = QWidget()
        hw_lay = QHBoxLayout(page_hw)
        hw_lay.setContentsMargins(0, 0, 0, 0)
        hw_lay.setSpacing(t.GAP)
        self.keyboard_widget = KeyboardHeatmapWidget(page_hw)
        self.mouse_widget = MouseHeatmapWidget(page_hw)
        hw_lay.addWidget(self.keyboard_widget, 72)
        hw_lay.addWidget(self.mouse_widget, 28)
        self.view_stack.addWidget(page_hw)

        page_cal = QWidget()
        cal_lay = QVBoxLayout(page_cal)
        cal_lay.setContentsMargins(0, 0, 0, 0)
        cal_lay.setSpacing(t.GAP)
        self.heatmap_calendar = HeatmapGridWidget(page_cal)
        cal_lay.addWidget(self.heatmap_calendar, 5)

        chart_card = QFrame()
        chart_card.setProperty("class", "Card")
        ch_lay = QVBoxLayout(chart_card)
        ch_lay.setContentsMargins(t.PAD, t.PAD, t.PAD, 14)
        ch_lay.setSpacing(12)
        hdr, self.ch_title_lbl, _ = card_header(INPUT_TITLES["day"], "Keys + clicks")
        ch_lay.addLayout(hdr)
        self.input_bars = BarChart(value=input_value, color=t.SERIES_KEYS, axis_format=format_number, parent=chart_card)
        self.input_bars.setAccessibleName("Key presses and clicks over the selected range")
        ch_lay.addWidget(self.input_bars, 1)
        cal_lay.addWidget(chart_card, 5)
        self.view_stack.addWidget(page_cal)

        main_lay.addWidget(self.view_stack, 1)

    def _switch_view(self, index: int):
        changed = index != self.view_stack.currentIndex()
        self.view_stack.setCurrentIndex(index)
        self.btn_view_hardware.setChecked(index == 0)
        self.btn_view_calendar.setChecked(index == 1)
        if changed:
            self.view_changed.emit(index)  # owner fetches the newly visible view's data
            t.fade_in(self.view_stack.currentWidget())

    def update_data(
        self,
        keys: int,
        clicks: int,
        scrolls: int,
        key_heatmap: Optional[Dict[int, int]],
        mouse_heatmap: Optional[Dict[str, int]],
        calendar_heatmap: Optional[List[Dict[str, Any]]],
        timeline: List[Dict[str, Any]],
        range_type: str = "day"
    ):
        self.card_keys.set_value(format_number(keys), "Key presses")
        self.card_clicks.set_value(format_number(clicks), "Mouse button presses")
        self.card_scrolls.set_value(format_number(scrolls), "Wheel steps")
        # None = that view isn't visible, so its data wasn't fetched
        if key_heatmap is not None:
            self.keyboard_widget.update_data(key_heatmap, range_type)
        if mouse_heatmap is not None:
            self.mouse_widget.update_data(mouse_heatmap, range_type)
        if calendar_heatmap is not None:
            self.heatmap_calendar.update_data(calendar_heatmap)
            self.ch_title_lbl.setText(INPUT_TITLES.get(range_type, "Input activity"))
            self.input_bars.set_data(timeline, range_type)

from typing import List, Dict, Any
from PyQt6.QtWidgets import QFrame, QVBoxLayout
from .. import theme as t
from .bar_chart import BarChart
from .common import card_header

RANGE_TITLES = {
    "day": ("Hourly activity", "Active time per hour"),
    "week": ("Daily activity", "7-day window"),
    "month": ("Daily activity", "30-day window"),
    "year": ("Monthly activity", "Last 12 months"),
    "all_time": ("Activity over time", "By month, or by year once history spans more than 12 months"),
}


class HourlyTimelineWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "Card")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.PAD, t.PAD, t.PAD, 14)
        lay.setSpacing(12)
        hdr, self.title_lbl, self.sub_lbl = card_header(*RANGE_TITLES["day"])
        lay.addLayout(hdr)

        self.painter_widget = BarChart(parent=self)
        self.painter_widget.setAccessibleName("Screen time over the selected range")
        lay.addWidget(self.painter_widget, 1)

    def update_data(self, timeline_data: List[Dict[str, Any]], range_type: str = "day", is_today: bool = True):
        t_title, t_sub = RANGE_TITLES.get(range_type, ("Activity", ""))
        self.title_lbl.setText(t_title)
        self.sub_lbl.setText(t_sub)
        self.painter_widget.set_data(timeline_data, range_type)

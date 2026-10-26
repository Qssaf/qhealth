import datetime
from typing import Dict, Any, Callable, List
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QProgressBar, QCheckBox, QSizePolicy, QScrollArea
)
from qhealth_core.db import set_app_budget, extend_app_budget
from .. import theme as t
from ..icons import icon
from ..utils import format_duration, format_number, get_app_icon_pixmap, category_badge_html
from .bar_chart import BarChart
from .common import ShareBar, card_header, sync_rows
from .stat_cards import StatCard

RANGE_LABELS = {
    "day": "Screen time · day",
    "week": "Screen time · 7 days",
    "month": "Screen time · 30 days",
    "year": "Screen time · last 12 months",
    "all_time": "Screen time · all time"
}

TREND_TITLES = {
    "day": "Usage by hour",
    "week": "Usage by day",
    "month": "Usage by day",
    "year": "Usage by month",
    "all_time": "Usage by month"
}

EXTENSION_MINUTES = 15

BUDGET_PRESETS = [
    (0, "No limit"),
    (30, "30 min / day"),
    (60, "1 hour / day"),
    (90, "1.5 hours / day"),
    (120, "2 hours / day"),
    (180, "3 hours / day"),
    (240, "4 hours / day"),
    (300, "5 hours / day")
]


class PageRowWidget(QFrame):
    """One website / channel / window-title group inside the drilldown."""

    def __init__(self, group_data: Dict[str, Any] = None, parent=None):
        super().__init__(parent)
        self.setProperty("class", "Static")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(7)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        self.icon_lbl = t.label("", "body")
        top_row.addWidget(self.icon_lbl)
        self.grp_lbl = t.label("", "h3")
        top_row.addWidget(self.grp_lbl, 1)
        self.dur_lbl = t.label("", "mono-strong")
        self.pct_lbl = t.label("", "caption")
        self.pct_lbl.setFixedWidth(46)
        self.pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(self.dur_lbl)
        top_row.addWidget(self.pct_lbl)
        lay.addLayout(top_row)

        bot_row = QHBoxLayout()
        bot_row.setSpacing(12)
        self.p_bar = ShareBar(t.SERIES_TIME)
        bot_row.addWidget(self.p_bar, 1)
        self.k_lbl = t.label("", "caption")
        bot_row.addWidget(self.k_lbl)
        lay.addLayout(bot_row)

        if group_data:
            self.set_data(group_data)

    def set_data(self, group_data: Dict[str, Any]):
        group_name = group_data.get("group_name") or group_data.get("clean_title", "Unknown Website")
        dur = group_data.get("duration", 0)
        pct = group_data.get("percentage", 0.0)
        keys = group_data.get("keystrokes", 0)
        clicks = group_data.get("clicks", 0)

        self.icon_lbl.setText(group_data.get("icon", "🌐"))
        self.grp_lbl.setText(group_name if len(group_name) <= 50 else group_name[:47] + "...")
        self.grp_lbl.setToolTip(group_name if len(group_name) > 50 else "")
        self.dur_lbl.setText(format_duration(dur))
        self.pct_lbl.setText(f"{pct}%")
        self.p_bar.set_value(max(1.0, pct) if dur > 0 else 0)
        self.k_lbl.setVisible(keys > 0 or clicks > 0)
        self.k_lbl.setText(f"{format_number(keys)} keys · {format_number(clicks)} clicks")


class AppDetailView(QWidget):
    def __init__(self, on_back: Callable[[], None], parent=None):
        super().__init__(parent)
        self.on_back = on_back
        self.current_app_id = ""
        self._last_duration = 0
        self._last_range_type = "day"
        self._is_updating = False
        self._last_target_date = ""
        self._last_extra_minutes = 0
        self._is_terminal = False
        self.page_rows: List[PageRowWidget] = []

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(10)

        # 1. Back
        back_bar = QHBoxLayout()
        self.btn_back = QPushButton("All applications")
        self.btn_back.setProperty("class", "Ghost")
        self.btn_back.setIcon(icon("back", t.TEXT_2, size=16))
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setToolTip("Back to the applications list (Alt+Left)")
        self.btn_back.setShortcut("Alt+Left")
        self.btn_back.clicked.connect(self.on_back)
        back_bar.addWidget(self.btn_back)
        back_bar.addStretch()
        root_lay.addLayout(back_bar)

        self.loading_bar = QProgressBar(self)
        self.loading_bar.setFixedHeight(2)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setVisible(False)
        root_lay.addWidget(self.loading_bar)

        # 2. Scrollable body
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        main_lay = QVBoxLayout(self.scroll_content)
        main_lay.setContentsMargins(0, 0, 8, 0)
        main_lay.setSpacing(t.GAP)
        self.scroll_area.setWidget(self.scroll_content)
        root_lay.addWidget(self.scroll_area, 1)

        # Hero
        self.hero_card = QFrame()
        self.hero_card.setProperty("class", "Card")
        hero_lay = QHBoxLayout(self.hero_card)
        hero_lay.setContentsMargins(t.PAD, t.PAD, t.PAD + 4, t.PAD)
        hero_lay.setSpacing(16)

        icon_tile = QFrame()
        icon_tile.setProperty("class", "Tile")
        icon_tile.setFixedSize(60, 60)
        it_lay = QVBoxLayout(icon_tile)
        it_lay.setContentsMargins(0, 0, 0, 0)
        self.app_icon = t.label()
        self.app_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        it_lay.addWidget(self.app_icon)
        hero_lay.addWidget(icon_tile)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        self.name_lbl = t.label("Application", "h1")
        sub_title_row = QHBoxLayout()
        sub_title_row.setSpacing(8)
        self.category_badge = t.label("", "badge")
        self.category_badge.setTextFormat(Qt.TextFormat.RichText)
        sub_title_row.addWidget(self.category_badge)
        self.id_lbl = t.label("app.id", "mono")
        sub_title_row.addWidget(self.id_lbl)
        sub_title_row.addStretch()
        title_box.addWidget(self.name_lbl)
        title_box.addLayout(sub_title_row)
        hero_lay.addLayout(title_box, 1)

        dur_box = QVBoxLayout()
        dur_box.setSpacing(2)
        self.range_tag_lbl = t.label("Screen time · day", "caption")
        self.range_tag_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.total_dur_lbl = t.label("0h 0m", "metric")
        self.total_dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        dur_box.addWidget(self.range_tag_lbl)
        dur_box.addWidget(self.total_dur_lbl)
        hero_lay.addLayout(dur_box)
        main_lay.addWidget(self.hero_card)

        # Daily limit
        self.budget_card = QFrame()
        self.budget_card.setProperty("class", "Card")
        b_lay = QVBoxLayout(self.budget_card)
        b_lay.setContentsMargins(t.PAD, 16, t.PAD, 16)
        b_lay.setSpacing(10)

        b_top = QHBoxLayout()
        b_title_box = QVBoxLayout()
        b_title_box.setSpacing(2)
        b_title_box.addWidget(t.label("Daily limit", "h2"))
        b_title_box.addWidget(t.label("Set a daily allowance for this app, and optionally close it once the limit is hit.", "caption"))
        b_top.addLayout(b_title_box, 1)

        self.budget_combo = QComboBox()
        for mins, text in BUDGET_PRESETS:
            self.budget_combo.addItem(text, mins)
        self.budget_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.budget_combo.setMinimumWidth(150)
        self.budget_combo.setAccessibleName("Daily time limit")
        self.budget_combo.currentIndexChanged.connect(self._on_budget_changed)
        b_top.addWidget(self.budget_combo, 0, Qt.AlignmentFlag.AlignTop)
        b_lay.addLayout(b_top)

        self.budget_progress_box = QVBoxLayout()
        self.budget_progress_box.setSpacing(6)
        self.budget_status_lbl = t.label("No daily limit set", "caption")
        self.budget_bar = QProgressBar()
        self.budget_bar.setFixedHeight(6)
        self.budget_bar.setTextVisible(False)
        self.budget_bar.setMaximum(100)
        self.budget_bar.setValue(0)
        status_row = QHBoxLayout()
        status_row.addWidget(self.budget_status_lbl, 1)
        self.extend_btn = QPushButton(f"+{EXTENSION_MINUTES} min today")
        self.extend_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.extend_btn.setToolTip("Allow this app a little longer today; the limit is back to normal tomorrow.")
        self.extend_btn.clicked.connect(self._on_extend_clicked)
        self.extend_btn.setVisible(False)
        status_row.addWidget(self.extend_btn)
        self.budget_progress_box.addLayout(status_row)
        self.budget_progress_box.addWidget(self.budget_bar)
        self.terminal_note = t.label("Terminals are never force-closed; this limit only sends reminders.", "caption")
        self.terminal_note.setVisible(False)
        self.budget_progress_box.addWidget(self.terminal_note)

        self.block_checkbox = QCheckBox("Force close this app when the daily limit is reached")
        self.block_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.block_checkbox.toggled.connect(self._on_block_checkbox_toggled)
        self.budget_progress_box.addWidget(self.block_checkbox)
        b_lay.addLayout(self.budget_progress_box)
        main_lay.addWidget(self.budget_card)

        # Totals
        stats_row = QHBoxLayout()
        stats_row.setSpacing(t.GAP)
        self.card_keys = StatCard("KEYSTROKES", t.SERIES_KEYS)
        self.card_clicks = StatCard("CLICKS", t.SERIES_CLICKS)
        self.card_days = StatCard("ACTIVE DAYS", t.SERIES_TIME)
        for card in (self.card_keys, self.card_clicks, self.card_days):
            stats_row.addWidget(card, 1)
        main_lay.addLayout(stats_row)

        # Usage trend
        trend_card = QFrame()
        trend_card.setProperty("class", "Card")
        tr_lay = QVBoxLayout(trend_card)
        tr_lay.setContentsMargins(t.PAD, t.PAD, t.PAD, 14)
        tr_lay.setSpacing(12)
        hdr, self.trend_title_lbl, _ = card_header("Usage", "Active time")
        tr_lay.addLayout(hdr)
        self.trend_painter = BarChart(parent=trend_card)
        self.trend_painter.setMinimumHeight(170)
        self.trend_painter.setAccessibleName("This app's screen time over the selected range")
        tr_lay.addWidget(self.trend_painter)
        main_lay.addWidget(trend_card)

        # Websites / channels / pages
        self.pages_card = QFrame()
        self.pages_card.setProperty("class", "Card")
        self.pages_lay = QVBoxLayout(self.pages_card)
        self.pages_lay.setContentsMargins(t.PAD, t.PAD, t.PAD, t.PAD)
        self.pages_lay.setSpacing(10)
        p_hdr_row, self.pages_hdr_lbl, self.pages_count_lbl = card_header("Websites, channels & windows", "0 items")
        self.pages_lay.addLayout(p_hdr_row)
        self.pages_box = QVBoxLayout()
        self.pages_box.setSpacing(6)
        self.pages_lay.addLayout(self.pages_box)
        self.pages_empty_lbl = t.label("No detailed window activity or websites recorded in this range.", "empty")
        self.pages_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pages_lay.addWidget(self.pages_empty_lbl)
        main_lay.addWidget(self.pages_card)
        main_lay.addStretch()

    def _on_budget_changed(self, idx: int):
        if self._is_updating or not self.current_app_id:
            return
        limit_mins = self.budget_combo.currentData()
        if limit_mins is None:
            limit_mins = 0
        block_on_exceed = self.block_checkbox.isChecked() if limit_mins > 0 else True
        # PyQt aborts the app on an exception escaping a slot; a locked DB must not do that
        try:
            set_app_budget(self.current_app_id, limit_mins, enabled=(limit_mins > 0), block_on_exceed=block_on_exceed)
        except Exception:
            return
        self._update_block_option_visibility(limit_mins)
        self._update_budget_ui(self._last_duration, limit_mins, self._last_range_type)

    def _update_block_option_visibility(self, limit_mins: int):
        self.block_checkbox.setVisible(limit_mins > 0 and not self._is_terminal)
        self.terminal_note.setVisible(limit_mins > 0 and self._is_terminal)

    def _on_block_checkbox_toggled(self, checked: bool):
        if self._is_updating or not self.current_app_id:
            return
        limit_mins = self.budget_combo.currentData() or 0
        try:
            set_app_budget(self.current_app_id, limit_mins, enabled=(limit_mins > 0), block_on_exceed=checked)
        except Exception:
            pass

    def _on_extend_clicked(self):
        if not self.current_app_id:
            return
        try:
            extend_app_budget(self.current_app_id, EXTENSION_MINUTES)
        except Exception:
            return
        self._last_extra_minutes += EXTENSION_MINUTES
        self._update_budget_ui(self._last_duration, self.budget_combo.currentData() or 0, self._last_range_type)

    def _is_viewing_today(self) -> bool:
        return not self._last_target_date or self._last_target_date == datetime.date.today().strftime("%Y-%m-%d")

    def _update_budget_ui(self, dur: int, limit_mins: int, range_type: str = "day"):
        # Extensions are granted per day, so they only change the Day view's limit
        extra_mins = self._last_extra_minutes if (range_type == "day" and limit_mins > 0) else 0
        self.extend_btn.setVisible(
            range_type == "day" and limit_mins > 0 and self._is_viewing_today()
            and dur >= (limit_mins + extra_mins) * 60
        )
        limit_mins += extra_mins
        self.budget_bar.setVisible(limit_mins > 0 and range_type != "all_time")
        if limit_mins > 0 and range_type == "all_time":
            # A lifetime total can't be compared against a per-day limit
            self.budget_bar.setValue(0)
            self.budget_status_lbl.setText(f"Daily limit: {format_duration(limit_mins * 60)} (see the Day view for usage)")
        elif limit_mins > 0:
            range_days = 1
            if range_type == "week":
                range_days = 7
            elif range_type == "month":
                range_days = 30
            elif range_type == "year":
                range_days = 365

            limit_secs = limit_mins * 60 * range_days
            pct = min(100, int((dur / float(limit_secs)) * 100)) if limit_secs > 0 else 0
            self.budget_bar.setValue(pct)
            t.set_prop(self.budget_bar, "tone", "good" if pct < 80 else ("warn" if pct < 100 else "bad"))
            if range_type != "day":
                label_suffix = f"in {range_type.replace('_', ' ')}"
            elif not self._is_viewing_today():
                label_suffix = f"on {self._last_target_date}"
            else:
                label_suffix = "today"
            extra_note = f" · +{extra_mins}m extension" if extra_mins else ""
            self.budget_status_lbl.setText(f"Used {label_suffix}: {format_duration(dur)} of {format_duration(limit_secs)} ({pct}%){extra_note}")
        else:
            self.budget_bar.setValue(0)
            self.budget_status_lbl.setText("No daily limit set for this app.")

    def show_loading(self):
        self.loading_bar.setVisible(True)

    def set_app_data(self, data: Dict[str, Any], range_type: str = "day"):
        self.loading_bar.setVisible(False)
        app_name = data.get("display_name", "Unknown")
        icon_name = data.get("icon", "")
        app_id = data.get("app_id", "")

        if self.current_app_id != app_id:
            self.scroll_area.verticalScrollBar().setValue(0)

        self.current_app_id = app_id
        self._last_range_type = range_type
        self._last_target_date = data.get("target_date", "")
        self._last_extra_minutes = data.get("budget_extra_minutes", 0)
        self._is_terminal = bool(data.get("is_terminal", False))

        self.name_lbl.setText(app_name)
        self.id_lbl.setText(app_id)
        self.app_icon.setPixmap(get_app_icon_pixmap(icon_name, app_name, 44))
        self.category_badge.setText(category_badge_html(data.get("category", "Application")))

        r_tag = RANGE_LABELS.get(range_type, "Screen time")
        if range_type == "day" and not self._is_viewing_today():
            r_tag = f"Screen time · {self._last_target_date}"
        self.range_tag_lbl.setText(r_tag)
        self.trend_title_lbl.setText(TREND_TITLES.get(range_type, "Usage"))

        dur = data.get("total_duration", 0)
        self._last_duration = dur
        self.total_dur_lbl.setText(format_duration(dur))
        self.card_keys.set_value(format_number(data.get("total_keystrokes", 0)), "In this range")
        self.card_clicks.set_value(format_number(data.get("total_clicks", 0)), "In this range")
        active_days = data.get("active_days", 0)
        self.card_days.set_value(f"{active_days} day{'s' if active_days != 1 else ''}", "With any activity")

        # Budget section
        self._is_updating = True
        budget_info = data.get("budget") or {}
        limit_mins = budget_info.get("daily_limit_minutes", 0) if budget_info.get("enabled", 1) else 0
        block_on_exceed = bool(budget_info.get("block_on_exceed", 1))

        idx = self.budget_combo.findData(limit_mins)
        if idx < 0 and limit_mins > 0:
            # Limit outside the presets (older version or manual DB edit): show it, not "No limit"
            self.budget_combo.addItem(f"{limit_mins} min / day", limit_mins)
            idx = self.budget_combo.findData(limit_mins)
        self.budget_combo.setCurrentIndex(max(idx, 0))
        self.block_checkbox.setChecked(block_on_exceed)
        self._update_block_option_visibility(limit_mins)
        self._is_updating = False

        self._update_budget_ui(dur, limit_mins, range_type)

        self.trend_painter.set_data(data.get("timeline", []), range_type)

        pages = data.get("pages_breakdown", [])
        self.pages_count_lbl.setText(f"{len(pages)} item{'s' if len(pages) != 1 else ''}")
        self.pages_empty_lbl.setVisible(not pages)
        sync_rows(self.page_rows, self.pages_box, [(p,) for p in pages], lambda: PageRowWidget(parent=self.pages_card))

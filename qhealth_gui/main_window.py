import json
import datetime
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QDate
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QDateEdit, QFrame, QApplication, QSizePolicy
)
from PyQt6.QtGui import QIcon, QKeySequence, QPixmap, QPainter, QColor, QShortcut

from qhealth_core.db import (
    get_stats_by_range, get_activity_heatmap_data, get_app_detail_stats,
    get_keyboard_heatmap_data, get_mouse_heatmap_data, toggle_pause_setting, is_paused_setting,
    get_activity_streak_stats
)

from .styles import get_qhealth_stylesheet
from .widgets.live_pulse import LivePulseWidget
from .widgets.stat_cards import StatCardsWidget
from .widgets.radial_chart import RadialChartWidget
from .widgets.hourly_timeline import HourlyTimelineWidget
from .widgets.app_leaderboard import AppLeaderboardWidget
from .widgets.input_analytics import InputAnalyticsWidget
from .widgets.app_detail_view import AppDetailView
from .widgets.glowing_calendar import GlowingDatePickerBtn

STATE_FILE = Path.home() / ".local" / "share" / "qhealth" / "live_state.json"

def create_app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    painter.setBrush(QColor(15, 23, 42))
    painter.setPen(QColor(30, 41, 59))
    painter.drawRoundedRect(2, 2, 60, 60, 16, 16)
    
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(16, 185, 129))
    painter.drawEllipse(12, 12, 40, 40)
    
    painter.setBrush(QColor(10, 13, 20))
    painter.drawEllipse(18, 18, 28, 28)
    
    painter.setBrush(QColor(6, 182, 212))
    painter.drawEllipse(27, 27, 10, 10)
    
    painter.end()
    return QIcon(pixmap)

class QHealthMainWindow(QMainWindow):
    def __init__(self, tracker=None):
        super().__init__()
        self.tracker = tracker
        self.current_range = "day" # day, week, month, year, all_time
        self.selected_date = datetime.date.today().strftime("%Y-%m-%d")
        self.active_drilldown_app_id = ""

        self.setWindowTitle("QHealth")
        self.resize(1180, 820)
        self.setMinimumSize(980, 700)
        self.icon = create_app_icon()
        self.setWindowIcon(self.icon)

        self.setStyleSheet(get_qhealth_stylesheet())

        # Central Layout
        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(20, 16, 20, 16)
        root_lay.setSpacing(14)

        # 1. Header Bar
        self._build_header(root_lay)

        # 2. Main Page Stack (Overview, Input & Heatmap, Apps)
        self.main_stack = QStackedWidget()

        # --- PAGE 1: OVERVIEW ---
        page_overview = QWidget()
        ov_lay = QVBoxLayout(page_overview)
        ov_lay.setContentsMargins(0, 0, 0, 0)
        ov_lay.setSpacing(14)

        self.live_widget = LivePulseWidget(page_overview)
        ov_lay.addWidget(self.live_widget)

        self.stat_cards = StatCardsWidget(page_overview)
        ov_lay.addWidget(self.stat_cards)

        mid_row = QHBoxLayout()
        mid_row.setSpacing(14)
        self.radial_widget = RadialChartWidget(page_overview)
        self.timeline_widget = HourlyTimelineWidget(page_overview)
        mid_row.addWidget(self.radial_widget, 4)
        mid_row.addWidget(self.timeline_widget, 6)
        ov_lay.addLayout(mid_row)
        ov_lay.addStretch()

        self.main_stack.addWidget(page_overview)

        # --- PAGE 2: INPUT & HEATMAP ---
        page_input = QWidget()
        in_lay = QVBoxLayout(page_input)
        in_lay.setContentsMargins(0, 0, 0, 0)
        in_lay.setSpacing(14)

        self.input_page_widget = InputAnalyticsWidget(page_input)
        in_lay.addWidget(self.input_page_widget)
        in_lay.addStretch()

        self.main_stack.addWidget(page_input)

        # --- PAGE 3: APPLICATIONS ---
        page_apps = QWidget()
        apps_lay = QVBoxLayout(page_apps)
        apps_lay.setContentsMargins(0, 0, 0, 0)
        apps_lay.setSpacing(14)

        self.apps_sub_stack = QStackedWidget()
        
        # Sub-view 0: All apps list
        self.apps_leaderboard = AppLeaderboardWidget(on_app_click=self._on_app_selected, parent=page_apps)
        self.apps_sub_stack.addWidget(self.apps_leaderboard)

        # Sub-view 1: Single app drilldown detail view
        self.app_detail_view = AppDetailView(on_back=self._on_back_to_apps_list, parent=page_apps)
        self.apps_sub_stack.addWidget(self.app_detail_view)

        apps_lay.addWidget(self.apps_sub_stack)
        self.main_stack.addWidget(page_apps)

        root_lay.addWidget(self.main_stack, 1)

        # Shortcuts (Esc and Ctrl+W close window)
        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        self.shortcut_esc.activated.connect(self.close)

        self.shortcut_close = QShortcut(QKeySequence("Ctrl+W"), self)
        self.shortcut_close.activated.connect(self.close)

        # Timers (Both synced to 3 seconds)
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self._poll_live)
        self.live_timer.start(3000)

        self.db_timer = QTimer(self)
        self.db_timer.timeout.connect(self._poll_db)
        self.db_timer.start(3000)

        # Initial Load
        self._poll_live()
        self._poll_db()

    def _build_header(self, parent_layout: QVBoxLayout):
        hdr = QHBoxLayout()
        hdr.setSpacing(14)

        # Brand Title & Streak Badge
        brand_box = QHBoxLayout()
        brand_box.setSpacing(10)
        logo_lbl = QLabel()
        logo_lbl.setPixmap(self.icon.pixmap(26, 26))
        title_lbl = QLabel("QHEALTH")
        title_lbl.setStyleSheet("font-size: 17px; font-weight: 900; color: #ffffff; letter-spacing: 0.5px;")

        self.streak_badge = QLabel("🌱 Day 0")
        self.streak_badge.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; background-color: rgba(148,163,184,0.12); border: 1px solid rgba(148,163,184,0.25); padding: 3px 8px; border-radius: 6px; font-family: 'Inter', sans-serif;")

        brand_box.addWidget(logo_lbl)
        brand_box.addWidget(title_lbl)
        brand_box.addWidget(self.streak_badge)
        hdr.addLayout(brand_box)

        hdr.addStretch()

        # 1. Page Switcher Tabs (Overview | Input & Heatmap | Applications)
        pages_box = QFrame()
        pages_box.setProperty("class", "GlassCardInner")
        pages_box.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        p_lay = QHBoxLayout(pages_box)
        p_lay.setContentsMargins(4, 3, 4, 3)
        p_lay.setSpacing(4)

        self.btn_page_overview = QPushButton("Overview")
        self.btn_page_overview.setProperty("class", "TabBtn")
        self.btn_page_overview.setCheckable(True)
        self.btn_page_overview.setChecked(True)
        self.btn_page_overview.setMinimumWidth(75)
        self.btn_page_overview.clicked.connect(lambda: self._switch_main_page(0))

        self.btn_page_input = QPushButton("Input & Heatmap")
        self.btn_page_input.setProperty("class", "TabBtn")
        self.btn_page_input.setCheckable(True)
        self.btn_page_input.setMinimumWidth(130)
        self.btn_page_input.clicked.connect(lambda: self._switch_main_page(1))

        self.btn_page_apps = QPushButton("Applications")
        self.btn_page_apps.setProperty("class", "TabBtn")
        self.btn_page_apps.setCheckable(True)
        self.btn_page_apps.setMinimumWidth(95)
        self.btn_page_apps.clicked.connect(lambda: self._switch_main_page(2))

        p_lay.addWidget(self.btn_page_overview)
        p_lay.addWidget(self.btn_page_input)
        p_lay.addWidget(self.btn_page_apps)
        hdr.addWidget(pages_box)

        # 2. Time Range Switcher (Day | Week | Month | Year | All Time)
        range_box = QFrame()
        range_box.setProperty("class", "GlassCardInner")
        r_lay = QHBoxLayout(range_box)
        r_lay.setContentsMargins(4, 3, 4, 3)
        r_lay.setSpacing(2)

        self.range_btns = {}
        for r_code, r_label in [("day", "Day"), ("week", "Week"), ("month", "Month"), ("year", "Year"), ("all_time", "All Time")]:
            btn = QPushButton(r_label)
            btn.setProperty("class", "ActionBtn")
            btn.setCheckable(True)
            btn.setChecked(r_code == "day")
            btn.clicked.connect(lambda checked, code=r_code: self._set_range(code))
            r_lay.addWidget(btn)
            self.range_btns[r_code] = btn

        hdr.addWidget(range_box)

        # 3. Glowing Date Picker (only for day view)
        self.date_btn = GlowingDatePickerBtn(self.selected_date)
        self.date_btn.dateChanged.connect(self._on_date_changed)
        hdr.addWidget(self.date_btn)

        # 4. Pause / Resume Button
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setProperty("class", "ActionBtn")
        self.btn_pause.setCheckable(True)
        self.btn_pause.clicked.connect(self._on_toggle_pause)
        hdr.addWidget(self.btn_pause)

        parent_layout.addLayout(hdr)

    def _switch_main_page(self, index: int):
        self.main_stack.setCurrentIndex(index)
        self.btn_page_overview.setChecked(index == 0)
        self.btn_page_input.setChecked(index == 1)
        self.btn_page_apps.setChecked(index == 2)
        self._poll_db()

    def _set_range(self, range_code: str):
        self.current_range = range_code
        for code, btn in self.range_btns.items():
            btn.setChecked(code == range_code)
        self.date_btn.setVisible(range_code == "day")
        self._poll_db()

    def _on_date_changed(self, date_str: str):
        self.selected_date = date_str
        self._poll_db()

    def _on_toggle_pause(self):
        new_paused = toggle_pause_setting()
        if self.tracker:
            self.tracker.paused = new_paused
        self.btn_pause.setText("Resume" if new_paused else "Pause")
        self.btn_pause.setChecked(new_paused)

    def _on_app_selected(self, app_data: dict):
        app_id = app_data.get("app_id", "")
        self.active_drilldown_app_id = app_id
        detail_stats = get_app_detail_stats(app_id, self.current_range, self.selected_date)
        self.app_detail_view.set_app_data(detail_stats, self.current_range)
        self.apps_sub_stack.setCurrentIndex(1)

    def _on_back_to_apps_list(self):
        self.active_drilldown_app_id = ""
        self.apps_sub_stack.setCurrentIndex(0)

    def _poll_live(self):
        try:
            metrics = None
            if STATE_FILE.exists():
                try:
                    with open(STATE_FILE, "r") as f:
                        metrics = json.load(f)
                except Exception:
                    pass
            
            if not metrics and self.tracker:
                metrics = self.tracker.get_live_metrics()

            if metrics:
                self.live_widget.update_metrics(metrics)
                if metrics.get("is_paused") != self.btn_pause.isChecked():
                    self.btn_pause.setChecked(metrics.get("is_paused", False))
                    self.btn_pause.setText("Resume" if metrics.get("is_paused") else "Pause")
        except Exception:
            pass

    def _poll_db(self):
        try:
            stats = get_stats_by_range(self.current_range, self.selected_date)
            total_seconds = stats.get("total_duration", 0)
            categories = stats.get("categories", [])
            apps = stats.get("apps", [])
            timeline = stats.get("timeline", [])

            # Stat cards
            keys = stats.get("total_keystrokes", 0)
            clicks = stats.get("total_clicks", 0)
            scrolls = stats.get("total_scrolls", 0)
            focus_score = stats.get("focus_score", 100)
            focus_rating = stats.get("focus_rating", "Deep Work")
            top_app = apps[0] if apps else None
            top_name = top_app.get("app_name", "") if top_app else ""
            top_pct = top_app.get("percentage", 0.0) if top_app else 0.0

            try:
                streak_info = get_activity_streak_stats()
                streak_days = streak_info.get("current_streak", 0)
                if streak_days > 0:
                    self.streak_badge.setText(f"🔥 {streak_days}-Day Streak")
                    self.streak_badge.setStyleSheet("font-size: 10px; font-weight: 700; color: #f59e0b; background-color: rgba(245,158,11,0.15); border: 1px solid rgba(245,158,11,0.3); padding: 3px 8px; border-radius: 6px; font-family: 'Inter', sans-serif;")
                else:
                    self.streak_badge.setText("🌱 Day 0")
                    self.streak_badge.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; background-color: rgba(148,163,184,0.12); border: 1px solid rgba(148,163,184,0.25); padding: 3px 8px; border-radius: 6px; font-family: 'Inter', sans-serif;")
            except Exception:
                pass

            self.stat_cards.update_stats(total_seconds, keys, clicks, scrolls, top_name, top_pct, focus_score, focus_rating)
            self.radial_widget.update_data(total_seconds, apps, self.current_range)
            self.timeline_widget.update_data(timeline, self.current_range)

            # Update Input & Heatmap Page (Physical Keyboard, Mouse, Calendar Heatmap, Distribution)
            calendar_heatmap = get_activity_heatmap_data(days=70)
            key_heatmap = get_keyboard_heatmap_data(self.current_range, self.selected_date)
            mouse_heatmap = get_mouse_heatmap_data(self.current_range, self.selected_date)
            self.input_page_widget.update_data(
                keys, clicks, scrolls, key_heatmap, mouse_heatmap, calendar_heatmap, timeline, self.current_range
            )

            # Update Applications Page (Leaderboard & Active Drilldown)
            self.apps_leaderboard.update_apps(apps)
            if self.apps_sub_stack.currentIndex() == 1 and self.active_drilldown_app_id:
                detail_stats = get_app_detail_stats(self.active_drilldown_app_id, self.current_range, self.selected_date)
                self.app_detail_view.set_app_data(detail_stats, self.current_range)
        except Exception:
            pass

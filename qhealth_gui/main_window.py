import json
import time
import datetime
from PyQt6.QtCore import Qt, QTimer, QSize, QRectF
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout,
    QPushButton, QStackedWidget, QFrame, QApplication, QScrollArea
)
from PyQt6.QtGui import QIcon, QKeySequence, QPixmap, QPainter, QColor, QShortcut, QPen

from qhealth_core.db import (
    get_stats_by_range, get_activity_heatmap_data, get_app_detail_stats,
    get_keyboard_heatmap_data, get_mouse_heatmap_data, toggle_pause_setting,
    get_activity_streak_stats, get_focus_session, data_version
)

from qhealth_core.paths import STATE_FILE

from . import theme as t
from .icons import icon, toggle_icon
from .styles import apply_theme
from .widgets.live_pulse import LivePulseWidget
from .widgets.stat_cards import StatCardsWidget
from .widgets.radial_chart import RadialChartWidget
from .widgets.hourly_timeline import HourlyTimelineWidget
from .widgets.app_leaderboard import AppLeaderboardWidget
from .widgets.input_analytics import InputAnalyticsWidget
from .widgets.app_detail_view import AppDetailView
from .widgets.glowing_calendar import GlowingDatePickerBtn
from .widgets.focus_dialog import FocusModeDialog


PAGES = [("Overview", "overview"), ("Input", "input"), ("Applications", "apps")]
RANGES = [("day", "Day"), ("week", "Week"), ("month", "Month"), ("year", "Year"), ("all_time", "All time")]
RANGE_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}
WIDE = 1180  # below this window width, cards reflow into narrower arrangements


def create_app_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor(t.SURFACE))
    painter.setPen(QPen(QColor(t.BORDER_STRONG), 2))
    painter.drawRoundedRect(QRectF(2, 2, 60, 60), 16, 16)

    painter.setPen(QPen(QColor(t.RAISED), 7))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(15, 15, 34, 34))
    ring = QPen(QColor(t.ACCENT), 7)
    ring.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(ring)
    painter.drawArc(QRectF(15, 15, 34, 34), 90 * 16, -270 * 16)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(t.TEXT))
    painter.drawEllipse(QRectF(28, 28, 8, 8))
    painter.end()
    return QIcon(pixmap)


def _scrollable(page: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(page)
    return area


class QHealthMainWindow(QMainWindow):
    def __init__(self, tracker=None):
        super().__init__()
        self.tracker = tracker
        self.current_range = "day"  # day, week, month, year, all_time
        self.selected_date = datetime.date.today().strftime("%Y-%m-%d")
        self.active_drilldown_app_id = ""
        self._today_str = self.selected_date
        self.on_close = None  # set by the app to decide between quitting and staying in the tray
        self._data_version = None   # DB file signature at the last refresh
        self._last_streak_poll = 0.0  # streak only changes daily; re-query at most once a minute

        apply_theme(QApplication.instance())
        self.setWindowTitle("QHealth")
        self.resize(1280, 860)
        self.setMinimumSize(980, 680)
        self.icon = create_app_icon()
        self.setWindowIcon(self.icon)

        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QHBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        root_lay.addWidget(self._build_sidebar())

        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(28, 22, 28, 22)
        col.setSpacing(t.GAP)
        self._build_topbar(col)

        self.error_banner = t.label("", "banner")
        self.error_banner.setWordWrap(True)
        self.error_banner.hide()
        col.addWidget(self.error_banner)

        self.input_banner = t.label(
            "Keyboard and mouse activity isn't being recorded: your account can't read <b>/dev/input</b>. "
            "Run <b>sudo usermod -aG input $USER</b>, then log out and back in.", "banner")
        t.set_prop(self.input_banner, "tone", "warn")
        self.input_banner.setTextFormat(Qt.TextFormat.RichText)
        self.input_banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.input_banner.setWordWrap(True)
        self.input_banner.hide()  # shown when the tracker reports it can't open /dev/input
        col.addWidget(self.input_banner)

        self.main_stack = QStackedWidget()

        # --- PAGE 1: OVERVIEW ---
        page_overview = QWidget()
        ov_lay = QVBoxLayout(page_overview)
        ov_lay.setContentsMargins(0, 0, 6, 0)
        ov_lay.setSpacing(t.GAP)
        self.live_widget = LivePulseWidget(page_overview)
        ov_lay.addWidget(self.live_widget)
        self.stat_cards = StatCardsWidget(page_overview)
        ov_lay.addWidget(self.stat_cards)
        self.mid_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.mid_row.setSpacing(t.GAP)
        self.radial_widget = RadialChartWidget(page_overview, on_app_click=self._open_app_from_overview)
        self.timeline_widget = HourlyTimelineWidget(page_overview)
        self.radial_widget.setMinimumHeight(300)
        self.timeline_widget.setMinimumHeight(300)
        self.mid_row.addWidget(self.radial_widget, 5)
        self.mid_row.addWidget(self.timeline_widget, 6)
        ov_lay.addLayout(self.mid_row, 1)
        self.main_stack.addWidget(_scrollable(page_overview))

        # --- PAGE 2: INPUT & HEATMAP ---
        page_input = QWidget()
        in_lay = QVBoxLayout(page_input)
        in_lay.setContentsMargins(0, 0, 6, 0)
        self.input_page_widget = InputAnalyticsWidget(page_input)
        self.input_page_widget.view_changed.connect(lambda _: self._poll_db())
        self.input_page_widget.setMinimumHeight(520)
        in_lay.addWidget(self.input_page_widget)
        self.main_stack.addWidget(_scrollable(page_input))

        # --- PAGE 3: APPLICATIONS ---
        page_apps = QWidget()
        apps_lay = QVBoxLayout(page_apps)
        apps_lay.setContentsMargins(0, 0, 0, 0)
        self.apps_sub_stack = QStackedWidget()
        self.apps_leaderboard = AppLeaderboardWidget(on_app_click=self._on_app_selected, parent=page_apps)
        self.apps_sub_stack.addWidget(self.apps_leaderboard)
        self.app_detail_view = AppDetailView(on_back=self._on_back_to_apps_list, parent=page_apps)
        self.apps_sub_stack.addWidget(self.app_detail_view)
        apps_lay.addWidget(self.apps_sub_stack)
        self.main_stack.addWidget(page_apps)

        col.addWidget(self.main_stack, 1)
        root_lay.addWidget(content, 1)

        # Keyboard: Esc / Ctrl+W close, Ctrl+1..3 switch pages
        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        self.shortcut_esc.activated.connect(self.close)
        self.shortcut_close = QShortcut(QKeySequence("Ctrl+W"), self)
        self.shortcut_close.activated.connect(self.close)
        for i in range(len(PAGES)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self).activated.connect(lambda idx=i: self._switch_main_page(idx))

        # Buttons take focus from Tab only, so a mouse click doesn't leave a focus ring behind;
        # the window itself holds initial focus so nothing starts out ringed.
        for btn in self.findChildren(QPushButton):
            btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        central.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        central.setFocus()

        # Timers (Both synced to 3 seconds)
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self._poll_live)
        self.live_timer.start(3000)

        self.db_timer = QTimer(self)
        self.db_timer.timeout.connect(self._on_db_timer)
        self.db_timer.start(3000)

        # Data loads in showEvent (and again whenever the window is re-shown from the tray)
        self._refresh_header()

    # ------------------------------------------------------------------ layout
    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setProperty("class", "Sidebar")
        sidebar.setFixedWidth(224)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(14, 20, 14, 16)
        lay.setSpacing(4)

        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 0)
        brand.setSpacing(10)
        logo = t.label()
        logo.setPixmap(self.icon.pixmap(28, 28))
        brand.addWidget(logo)
        brand.addWidget(t.label("QHealth", "brand"))
        brand.addStretch()
        lay.addLayout(brand)
        lay.addSpacing(22)

        self.nav_btns = []
        for i, (title, icon_name) in enumerate(PAGES):
            btn = QPushButton(title)
            btn.setProperty("class", "Nav")
            btn.setCheckable(True)
            btn.setIcon(icon(icon_name, t.TEXT_3, on_color=t.ACCENT))
            btn.setIconSize(QSize(18, 18))
            btn.setMinimumHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"{title} (Ctrl+{i + 1})")
            btn.clicked.connect(lambda _, idx=i: self._switch_main_page(idx))
            lay.addWidget(btn)
            self.nav_btns.append(btn)
        self.btn_page_overview, self.btn_page_input, self.btn_page_apps = self.nav_btns
        self.btn_page_overview.setChecked(True)

        lay.addStretch()

        self.btn_focus = QPushButton("Focus session")
        self.btn_focus.setIcon(icon("focus", t.ACCENT))
        self.btn_focus.setIconSize(QSize(18, 18))
        self.btn_focus.setMinimumHeight(38)
        self.btn_focus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_focus.setToolTip("Block distracting apps for a set time")
        self.btn_focus.clicked.connect(self._open_focus_dialog)
        lay.addWidget(self.btn_focus)
        lay.addSpacing(12)

        divider = QFrame()
        divider.setProperty("class", "Divider")
        lay.addWidget(divider)
        lay.addSpacing(10)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(4, 0, 0, 0)
        self.status_lbl = t.label("● Waiting", "status")
        self.status_lbl.setToolTip("Live tracking status from the QHealth daemon")
        status_row.addWidget(self.status_lbl)
        status_row.addStretch()
        self.streak_badge = t.label("No streak yet", "badge")
        self.streak_badge.setToolTip("Consecutive days with recorded activity")
        status_row.addWidget(self.streak_badge)
        lay.addLayout(status_row)
        lay.addSpacing(8)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setProperty("class", "Ghost")
        self.btn_pause.setCheckable(True)
        self.btn_pause.setIcon(toggle_icon("pause", "play"))
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setToolTip("Pause or resume activity tracking")
        self.btn_pause.clicked.connect(self._on_toggle_pause)
        lay.addWidget(self.btn_pause)
        return sidebar

    def _build_topbar(self, parent_layout: QVBoxLayout):
        # Title left, controls right; controls drop to their own row on narrow windows
        self.topbar = bar = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        bar.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.page_title = t.label(PAGES[0][0], "h1")
        self.range_caption = t.label("", "caption")
        titles.addWidget(self.page_title)
        titles.addWidget(self.range_caption)
        bar.addLayout(titles)
        bar.addStretch()
        controls = QWidget()
        c_lay = QHBoxLayout(controls)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(12)

        range_box = QFrame()
        range_box.setProperty("class", "Segmented")
        r_lay = QHBoxLayout(range_box)
        r_lay.setContentsMargins(3, 3, 3, 3)
        r_lay.setSpacing(2)
        self.range_btns = {}
        for r_code, r_label in RANGES:
            btn = QPushButton(r_label)
            btn.setProperty("class", "Segment")
            btn.setCheckable(True)
            btn.setChecked(r_code == "day")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, code=r_code: self._set_range(code))
            r_lay.addWidget(btn)
            self.range_btns[r_code] = btn
        c_lay.addWidget(range_box)

        # Date stepper: ‹ [date] ›  (steps by the range length; hidden for All time)
        self.date_box = QWidget()
        d_lay = QHBoxLayout(self.date_box)
        d_lay.setContentsMargins(0, 0, 0, 0)
        d_lay.setSpacing(4)
        self.btn_prev_date = QPushButton()
        self.btn_next_date = QPushButton()
        self.date_btn = GlowingDatePickerBtn(self.selected_date)
        self.date_btn.dateChanged.connect(self._on_date_changed)
        for btn, name, step in ((self.btn_prev_date, "chevron-left", -1), (self.btn_next_date, "chevron-right", 1)):
            btn.setProperty("class", "Icon")
            btn.setIcon(icon(name, t.TEXT_2, size=16))
            btn.setFixedSize(32, 32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, s=step: self._step_date(s))
        self.date_btn.setMinimumHeight(32)
        d_lay.addWidget(self.btn_prev_date)
        d_lay.addWidget(self.date_btn)
        d_lay.addWidget(self.btn_next_date)
        c_lay.addWidget(self.date_box)
        bar.addWidget(controls, 0, Qt.AlignmentFlag.AlignLeft)

        parent_layout.addLayout(bar)

    def closeEvent(self, event):
        super().closeEvent(event)
        if self.on_close:
            self.on_close()

    def showEvent(self, event):
        # Polling pauses while hidden in the tray; catch up the moment the window comes back
        super().showEvent(event)
        self._poll_live()
        self._poll_db()

    def _is_shown(self) -> bool:
        return self.isVisible() and not self.isMinimized()

    def resizeEvent(self, event):
        wide = self.width() >= WIDE
        self.mid_row.setDirection(QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom)
        self.stat_cards.set_columns(4 if wide else 2)
        self.topbar.setDirection(QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom)
        super().resizeEvent(event)

    # ----------------------------------------------------------------- header
    def _roll_over_midnight(self):
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        if today_str != self._today_str:
            # Window left open past midnight: follow "today" if the user was viewing it
            if self.selected_date == self._today_str:
                self.selected_date = today_str
                self.date_btn.set_date_str(today_str)
            self._today_str = today_str
            self._refresh_header()

    def _refresh_header(self):
        try:
            anchor = datetime.datetime.strptime(self.selected_date, "%Y-%m-%d").date()
        except ValueError:
            anchor = datetime.date.today()
        today = datetime.date.today()
        if self.current_range == "day":
            caption = anchor.strftime("%A, %B %d, %Y") + (" · Today" if anchor == today else "")
        elif self.current_range == "all_time":
            caption = "Everything QHealth has recorded"
        else:
            days = RANGE_DAYS[self.current_range]
            start = anchor - datetime.timedelta(days=days - 1)
            caption = f"{start.strftime('%b %d, %Y')} – {anchor.strftime('%b %d, %Y')} · {days} days"
        self.range_caption.setText(caption)

        step = RANGE_DAYS.get(self.current_range, 1)
        unit = {1: "day", 7: "week", 30: "30 days", 365: "year"}[step]
        self.btn_prev_date.setToolTip(f"Previous {unit}")
        self.btn_next_date.setToolTip(f"Next {unit}")
        self.btn_prev_date.setAccessibleName(f"Previous {unit}")
        self.btn_next_date.setAccessibleName(f"Next {unit}")
        self.btn_next_date.setEnabled(anchor < today)
        self.date_box.setVisible(self.current_range != "all_time")

    def _step_date(self, direction: int):
        try:
            anchor = datetime.datetime.strptime(self.selected_date, "%Y-%m-%d").date()
        except ValueError:
            anchor = datetime.date.today()
        new_date = min(datetime.date.today(), anchor + datetime.timedelta(days=direction * RANGE_DAYS.get(self.current_range, 1)))
        date_str = new_date.strftime("%Y-%m-%d")
        self.date_btn.set_date_str(date_str)
        self._on_date_changed(date_str)

    # ------------------------------------------------------------- navigation
    def _switch_main_page(self, index: int):
        changed = index != self.main_stack.currentIndex()
        self.main_stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)
        self.page_title.setText(PAGES[index][0])
        if changed:
            t.fade_in(self.main_stack.currentWidget())
        self._poll_db()

    def _set_range(self, range_code: str):
        self.current_range = range_code
        for code, btn in self.range_btns.items():
            btn.setChecked(code == range_code)
        self._refresh_header()
        self._poll_db()

    def _on_date_changed(self, date_str: str):
        self.selected_date = date_str
        self._refresh_header()
        self._poll_db()

    def _on_toggle_pause(self):
        new_paused = toggle_pause_setting()
        if self.tracker:
            self.tracker.paused = new_paused
        self.btn_pause.setText("Resume" if new_paused else "Pause")
        self.btn_pause.setChecked(new_paused)

    def _open_app_from_overview(self, app_data: dict):
        self._switch_main_page(2)
        self._on_app_selected(app_data)

    def _on_app_selected(self, app_data: dict):
        app_id = app_data.get("app_id", "")
        self.active_drilldown_app_id = app_id
        detail_stats = get_app_detail_stats(app_id, self.current_range, self.selected_date)
        self.app_detail_view.set_app_data(detail_stats, self.current_range)
        if self.apps_sub_stack.currentIndex() != 1:
            self.apps_sub_stack.setCurrentIndex(1)
            t.fade_in(self.app_detail_view)

    def _on_back_to_apps_list(self):
        self.active_drilldown_app_id = ""
        self.apps_sub_stack.setCurrentIndex(0)
        t.fade_in(self.apps_leaderboard)
        # Reflect a budget edited in the detail view right away
        self._poll_db()

    def _open_focus_dialog(self):
        active_name = ""
        active_id = ""
        if hasattr(self, "live_widget"):
            active_name = self.live_widget.app_name_lbl.text()
            if hasattr(self.live_widget, "current_app_id"):
                active_id = self.live_widget.current_app_id

        dlg = FocusModeDialog(active_name, active_id, parent=self)
        dlg.session_changed.connect(self._on_focus_session_changed)
        dlg.exec()

    def _on_focus_session_changed(self):
        self._poll_live()

    # ---------------------------------------------------------------- polling
    def _poll_live(self):
        if not self._is_shown():
            return
        try:
            metrics = None
            try:
                # Ignore a leftover file from a daemon that died without cleanup (it heartbeats every 5 s)
                if time.time() - STATE_FILE.stat().st_mtime < 10:
                    with open(STATE_FILE, "r") as f:
                        metrics = json.load(f)
            except Exception:
                pass

            if not metrics and self.tracker:
                metrics = self.tracker.get_live_metrics()

            if metrics:
                self.live_widget.update_metrics(metrics)
                self.input_banner.setVisible(bool(metrics.get("input_access_denied")))
                if metrics.get("is_paused") != self.btn_pause.isChecked():
                    self.btn_pause.setChecked(metrics.get("is_paused", False))
                    self.btn_pause.setText("Resume" if metrics.get("is_paused") else "Pause")
                if metrics.get("is_paused"):
                    self.status_lbl.setText("● Paused")
                    t.set_prop(self.status_lbl, "tone", "warn")
                elif metrics.get("is_idle"):
                    self.status_lbl.setText("● Idle")
                    t.set_prop(self.status_lbl, "tone", "")
                else:
                    self.status_lbl.setText("● Tracking")
                    t.set_prop(self.status_lbl, "tone", "good")

            # Focus Mode button state
            focus_session = get_focus_session()
            if focus_session.get("active"):
                rem_secs = focus_session.get("remaining_seconds", 0)
                rem_mins = max(1, (rem_secs + 59) // 60)
                self.btn_focus.setText(f"Focusing · {rem_mins}m left")
                t.set_prop(self.btn_focus, "active", True)
            else:
                self.btn_focus.setText("Focus session")
                t.set_prop(self.btn_focus, "active", False)
        except Exception:
            pass

    def _on_db_timer(self):
        """3 s tick. Skipped while hidden, for ranges that ended on a past date, and whenever
        nothing was committed to the DB since the last refresh."""
        if not self._is_shown():
            return  # showEvent refreshes everything on the way back
        self._roll_over_midnight()
        # The streak is always "as of today", whatever date is being viewed
        self._refresh_streak()
        # Ranges ending on a past date can't change, so only explicit navigation reloads them.
        # All Time has no end date, so it still includes today.
        if self.selected_date < self._today_str and self.current_range != "all_time":
            return
        if data_version() == self._data_version:
            return
        self._poll_db()

    def _refresh_streak(self):
        # Streak scans every day's totals; once a minute is plenty
        if time.monotonic() - self._last_streak_poll < 60:
            return
        self._last_streak_poll = time.monotonic()
        try:
            streak_days = get_activity_streak_stats().get("current_streak", 0)
        except Exception:
            return
        self.streak_badge.setText(f"{streak_days}-day streak" if streak_days > 0 else "No streak yet")
        t.set_prop(self.streak_badge, "tone", "accent" if streak_days > 0 else "")

    def _poll_db(self):
        """Refresh only what's on screen (other pages refresh when switched to)."""
        self._refresh_streak()
        try:
            version = data_version()  # read first: a write landing mid-refresh triggers the next tick
            stats = get_stats_by_range(self.current_range, self.selected_date)
            total_seconds = stats.get("total_duration", 0)
            apps = stats.get("apps", [])
            timeline = stats.get("timeline", [])
            keys = stats.get("total_keystrokes", 0)
            clicks = stats.get("total_clicks", 0)
            scrolls = stats.get("total_scrolls", 0)

            page = self.main_stack.currentIndex()
            viewing_today = self.selected_date == self._today_str
            if page == 0:
                top_app = apps[0] if apps else {}
                self.stat_cards.update_stats(
                    total_seconds, keys, clicks, scrolls, top_app.get("app_name", ""), top_app.get("percentage", 0.0),
                    stats.get("focus_score", 0), stats.get("focus_rating", "No Activity"))
                self.radial_widget.update_data(total_seconds, apps, self.current_range)
                self.timeline_widget.update_data(timeline, self.current_range)
            elif page == 1:
                # Only the visible sub-view's heatmaps are queried
                hardware = self.input_page_widget.view_stack.currentIndex() == 0
                self.input_page_widget.update_data(
                    keys, clicks, scrolls,
                    get_keyboard_heatmap_data(self.current_range, self.selected_date) if hardware else None,
                    get_mouse_heatmap_data(self.current_range, self.selected_date) if hardware else None,
                    None if hardware else get_activity_heatmap_data(days=70, target_date=self.selected_date),
                    timeline, self.current_range,
                )
            else:
                # Only today's Day view can say an app is blocked right now
                self.apps_leaderboard.update_apps(apps, can_block=(self.current_range == "day" and viewing_today))
                if self.apps_sub_stack.currentIndex() == 1 and self.active_drilldown_app_id:
                    detail_stats = get_app_detail_stats(self.active_drilldown_app_id, self.current_range, self.selected_date)
                    self.app_detail_view.set_app_data(detail_stats, self.current_range)

            self._data_version = version
            self.error_banner.hide()
        except Exception as exc:
            self.error_banner.setText(f"Couldn't read activity data ({type(exc).__name__}). Showing the last good values; retrying every 3 seconds.")
            self.error_banner.show()

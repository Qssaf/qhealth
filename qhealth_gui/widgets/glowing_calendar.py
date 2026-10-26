import calendar
import datetime
from typing import Dict, Any
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtWidgets import QWidget, QDialog, QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QGridLayout
from qhealth_core.db import get_month_activity_map
from .. import theme as t
from ..icons import icon
from ..utils import format_duration, format_number
from .common import RampLegend

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

WEEKDAY_LABELS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


class GlowingDayCell(QPushButton):
    def __init__(self, day_num: int, date_str: str, is_current_month: bool, is_selected: bool, is_today: bool, activity: Dict[str, Any], parent=None):
        super().__init__(str(day_num) if (is_current_month and day_num > 0) else "", parent)
        self.date_str = date_str
        self.day_num = day_num
        self.is_current_month = is_current_month
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor if is_current_month else Qt.CursorShape.ArrowCursor)

        if not is_current_month:
            self.setStyleSheet("background: transparent; border: none;")
            self.setEnabled(False)
            return

        level = activity.get("level", 0) if activity else 0
        bg = t.heat(t.SERIES_TIME, level / 4.0) if level else None
        fg = t.ink_on(bg).name() if bg else t.TEXT_2
        if is_selected:
            border = f"2px solid {t.TEXT}"
        elif is_today:
            border = f"1px solid {t.ACCENT}"
        else:
            border = "1px solid transparent"
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg.name() if bg else 'transparent'}; color: {fg};
                border: {border}; border-radius: 8px; padding: 0px;
                font-size: 12px; font-weight: {600 if (is_today or is_selected) else 500};
            }}
            QPushButton:hover {{ border: {'2px' if is_selected else '1px'} solid {t.TEXT_2}; }}
            QPushButton:focus {{ border: 2px solid {t.ACCENT}; }}
        """)

        if activity and activity.get("duration", 0) > 0:
            self.setToolTip(
                f"{date_str}\nActive {format_duration(activity['duration'])}  ·  "
                f"{format_number(activity.get('keystrokes', 0))} keys  ·  {format_number(activity.get('clicks', 0))} clicks"
            )
        else:
            self.setToolTip(f"{date_str}\nNo screen time recorded")
        self.setAccessibleName(date_str)


class GlowingCalendarPopup(QDialog):
    dateSelected = pyqtSignal(str)

    def __init__(self, current_date_str: str, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        try:
            d = datetime.datetime.strptime(current_date_str, "%Y-%m-%d").date()
        except Exception:
            d = datetime.date.today()

        self.selected_date = d
        self.view_year = d.year
        self.view_month = d.month

        self.setStyleSheet(f"""
            QDialog {{ background: transparent; }}
            QFrame#CalendarContainer {{ background: {t.OVERLAY}; border: 1px solid {t.BORDER_STRONG}; border-radius: 14px; }}
        """)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setObjectName("CalendarContainer")
        self.c_lay = QVBoxLayout(self.container)
        self.c_lay.setContentsMargins(16, 14, 16, 14)
        self.c_lay.setSpacing(10)
        main_lay.addWidget(self.container)

        # 1. Header: ‹ Month Year › · Today
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        self.title_lbl = t.label("", "h2")
        hdr.addWidget(self.title_lbl, 1)

        self.btn_today = QPushButton("Today")
        self.btn_today.setProperty("class", "Ghost")
        self.btn_today.clicked.connect(self._go_today)
        hdr.addWidget(self.btn_today)

        self.btn_prev = QPushButton()
        self.btn_next = QPushButton()
        for btn, name, tip, slot in ((self.btn_prev, "chevron-left", "Previous month", self._prev_month),
                                     (self.btn_next, "chevron-right", "Next month", self._next_month)):
            btn.setProperty("class", "Icon")
            btn.setIcon(icon(name, t.TEXT_2, size=16))
            btn.setFixedSize(30, 30)
            btn.setToolTip(tip)
            btn.setAccessibleName(tip)
            btn.clicked.connect(slot)
            hdr.addWidget(btn)
        self.c_lay.addLayout(hdr)

        # 2. Weekday header
        w_hdr = QGridLayout()
        w_hdr.setSpacing(4)
        for col_idx, w_name in enumerate(WEEKDAY_LABELS):
            lbl = t.label(w_name, "overline")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedWidth(36)
            w_hdr.addWidget(lbl, 0, col_idx)
        self.c_lay.addLayout(w_hdr)

        # 3. Days grid
        self.grid_widget = QWidget()
        self.grid_lay = QGridLayout(self.grid_widget)
        self.grid_lay.setContentsMargins(0, 0, 0, 0)
        self.grid_lay.setSpacing(4)
        self.c_lay.addWidget(self.grid_widget)

        # 4. Legend
        leg_lay = QHBoxLayout()
        leg_lay.addWidget(t.label("Screen time", "caption"))
        leg_lay.addStretch()
        leg_lay.addWidget(RampLegend(t.SERIES_TIME))
        self.c_lay.addLayout(leg_lay)

        self._render_calendar()

    def _render_calendar(self):
        self.title_lbl.setText(f"{MONTH_NAMES[self.view_month]} {self.view_year}")
        month_activity = get_month_activity_map(self.view_year, self.view_month)

        while self.grid_lay.count():
            item = self.grid_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cal = calendar.Calendar(firstweekday=0)  # Monday first
        month_days = cal.monthdayscalendar(self.view_year, self.view_month)

        today = datetime.date.today()
        selected_str = self.selected_date.strftime("%Y-%m-%d")

        for row_idx, week in enumerate(month_days):
            for col_idx, day_num in enumerate(week):
                if day_num == 0:
                    cell = GlowingDayCell(0, "", False, False, False, {})
                else:
                    date_str = f"{self.view_year:04d}-{self.view_month:02d}-{day_num:02d}"
                    is_sel = (date_str == selected_str)
                    is_tod = (self.view_year == today.year and self.view_month == today.month and day_num == today.day)
                    act = month_activity.get(date_str, {})
                    cell = GlowingDayCell(day_num, date_str, True, is_sel, is_tod, act)
                    cell.clicked.connect(lambda checked, d=date_str: self._select_date(d))

                self.grid_lay.addWidget(cell, row_idx, col_idx)

    def _prev_month(self):
        self.view_month -= 1
        if self.view_month < 1:
            self.view_month = 12
            self.view_year -= 1
        self._render_calendar()

    def _next_month(self):
        self.view_month += 1
        if self.view_month > 12:
            self.view_month = 1
            self.view_year += 1
        self._render_calendar()

    def _go_today(self):
        today = datetime.date.today()
        self.view_year = today.year
        self.view_month = today.month
        self._select_date(today.strftime("%Y-%m-%d"))

    def _select_date(self, date_str: str):
        self.dateSelected.emit(date_str)
        self.accept()


class GlowingDatePickerBtn(QPushButton):
    dateChanged = pyqtSignal(str)

    def __init__(self, initial_date_str: str = "", parent=None):
        super().__init__(parent)
        self.setIcon(icon("calendar", t.TEXT_2, size=16))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Pick a date")
        self.current_date_str = initial_date_str if initial_date_str else datetime.date.today().strftime("%Y-%m-%d")
        self.clicked.connect(self._open_calendar_popup)
        self._update_button_label()

    def set_date_str(self, date_str: str):
        self.current_date_str = date_str
        self._update_button_label()

    def _update_button_label(self):
        try:
            d = datetime.datetime.strptime(self.current_date_str, "%Y-%m-%d").date()
            if d == datetime.date.today():
                formatted = f"Today · {d.strftime('%b %d')}"
            else:
                formatted = d.strftime("%a, %b %d, %Y")
        except Exception:
            formatted = self.current_date_str

        self.setText(formatted)
        self.setAccessibleName(f"Date: {formatted}. Open calendar")

    def _open_calendar_popup(self):
        popup = GlowingCalendarPopup(self.current_date_str, self)
        popup.dateSelected.connect(self._on_popup_date_selected)

        # Position popup below the button, clamped to screen bounds
        btn_pos = self.mapToGlobal(QPoint(0, self.height() + 6))
        if self.screen():
            geo = self.screen().availableGeometry()
            popup_w = 320
            popup_h = 380
            x = min(btn_pos.x(), geo.right() - popup_w - 8)
            x = max(geo.left() + 8, x)
            y = min(btn_pos.y(), geo.bottom() - popup_h - 8)
            y = max(geo.top() + 8, y)
            popup.move(QPoint(x, y))
        else:
            popup.move(btn_pos)

        popup.exec()

    def _on_popup_date_selected(self, date_str: str):
        self.set_date_str(date_str)
        self.dateChanged.emit(date_str)

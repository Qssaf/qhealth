import calendar
import datetime
from typing import Dict, Any, Callable, Optional
from PyQt6.QtCore import Qt, QDate, QPoint, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QDialog, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout, QSizePolicy
)
from PyQt6.QtGui import QColor, QFont, QCursor
from qhealth_core.db import get_month_activity_map
from ..utils import format_duration, format_number

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

GLOW_STYLES = {
    0: "background-color: rgba(22, 31, 48, 0.4); border: 1px solid rgba(255, 255, 255, 0.05); color: #94a3b8;",
    1: "background-color: #064e3b; border: 1px solid #047857; color: #a7f3d0;",
    2: "background-color: #047857; border: 1px solid #10b981; color: #ffffff;",
    3: "background-color: #059669; border: 1px solid #34d399; color: #ffffff; font-weight: bold;",
    4: "background-color: #10b981; border: 1px solid #6ee7b7; color: #ffffff; font-weight: 800;",
}

class GlowingDayCell(QPushButton):
    def __init__(self, day_num: int, date_str: str, is_current_month: bool, is_selected: bool, is_today: bool, activity: Dict[str, Any], parent=None):
        super().__init__(str(day_num), parent)
        self.date_str = date_str
        self.day_num = day_num
        self.is_current_month = is_current_month
        self.setFixedSize(38, 38)
        self.setCursor(Qt.CursorShape.PointingHandCursor if is_current_month else Qt.CursorShape.ArrowCursor)

        level = activity.get("level", 0) if (activity and is_current_month) else 0
        base_style = GLOW_STYLES.get(level, GLOW_STYLES[0])

        if not is_current_month:
            self.setStyleSheet("background-color: transparent; border: none; color: #334155;")
            self.setEnabled(False)
        else:
            border_extra = ""
            if is_selected:
                border_extra = "border: 2px solid #22d3ee; box-shadow: 0 0 10px #22d3ee;"
            elif is_today:
                border_extra = "border: 1.5px solid #fbbf24;"

            self.setStyleSheet(f"""
                QPushButton {{
                    {base_style}
                    border-radius: 8px;
                    font-family: 'Inter', sans-serif;
                    font-size: 12px;
                    {border_extra}
                }}
                QPushButton:hover {{
                    border: 1.5px solid #34d399;
                    background-color: rgba(16, 185, 129, 0.35);
                    color: #ffffff;
                }}
            """)

            # Tooltip with exact day metrics
            if activity and activity.get("duration", 0) > 0:
                dur_str = format_duration(activity["duration"])
                keys_str = format_number(activity.get("keystrokes", 0))
                clicks_str = format_number(activity.get("clicks", 0))
                self.setToolTip(f"📅 {date_str}\n⏱ Active: {dur_str}\n⌨ Keys: {keys_str} · 🖱 Clicks: {clicks_str}")
            else:
                self.setToolTip(f"📅 {date_str}\nNo screen time recorded")


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

        self.setStyleSheet("""
            QDialog {
                background: transparent;
            }
            QFrame#CalendarContainer {
                background-color: #0c1017;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 14px;
            }
            QPushButton.NavBtn {
                background-color: rgba(30, 41, 59, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.08);
                color: #cbd5e1;
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton.NavBtn:hover {
                background-color: rgba(51, 65, 85, 0.8);
                color: #ffffff;
                border-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton.TodayBtn {
                background-color: rgba(16, 185, 129, 0.15);
                border: 1px solid rgba(16, 185, 129, 0.3);
                color: #34d399;
                border-radius: 6px;
                padding: 3px 8px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton.TodayBtn:hover {
                background-color: rgba(16, 185, 129, 0.25);
                color: #ffffff;
            }
        """)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setObjectName("CalendarContainer")
        self.c_lay = QVBoxLayout(self.container)
        self.c_lay.setContentsMargins(16, 14, 16, 14)
        self.c_lay.setSpacing(12)
        main_lay.addWidget(self.container)

        # 1. Navigation Header (< Month Year > Today)
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        self.btn_prev = QPushButton("‹")
        self.btn_prev.setProperty("class", "NavBtn")
        self.btn_prev.clicked.connect(self._prev_month)
        hdr.addWidget(self.btn_prev)

        self.title_lbl = QLabel()
        self.title_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #ffffff;")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.addWidget(self.title_lbl, 1)

        self.btn_next = QPushButton("›")
        self.btn_next.setProperty("class", "NavBtn")
        self.btn_next.clicked.connect(self._next_month)
        hdr.addWidget(self.btn_next)

        self.btn_today = QPushButton("Today")
        self.btn_today.setProperty("class", "TodayBtn")
        self.btn_today.clicked.connect(self._go_today)
        hdr.addWidget(self.btn_today)

        self.c_lay.addLayout(hdr)

        # 2. Weekday Header Row (Mon..Sun)
        w_hdr = QGridLayout()
        w_hdr.setSpacing(6)
        for col_idx, w_name in enumerate(WEEKDAY_LABELS):
            lbl = QLabel(w_name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600;")
            w_hdr.addWidget(lbl, 0, col_idx)
        self.c_lay.addLayout(w_hdr)

        # 3. Days Grid
        self.grid_widget = QWidget()
        self.grid_lay = QGridLayout(self.grid_widget)
        self.grid_lay.setContentsMargins(0, 0, 0, 0)
        self.grid_lay.setSpacing(6)
        self.c_lay.addWidget(self.grid_widget)

        # 4. Glow Legend
        leg_lay = QHBoxLayout()
        leg_lay.setSpacing(6)
        leg_title = QLabel("Activity Glow:")
        leg_title.setStyleSheet("color: #64748b; font-size: 10px;")
        leg_lay.addWidget(leg_title)

        for lvl, bg_c in [(0, "#161f30"), (1, "#064e3b"), (2, "#047857"), (3, "#10b981"), (4, "#34d399")]:
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background-color: {bg_c}; border-radius: 2px;")
            leg_lay.addWidget(dot)

        leg_lay.addStretch()
        self.c_lay.addLayout(leg_lay)

        self._render_calendar()

    def _render_calendar(self):
        # Update Header Title
        self.title_lbl.setText(f"{MONTH_NAMES[self.view_month]} {self.view_year}")

        # Fetch month activity map from DB for glow levels
        month_activity = get_month_activity_map(self.view_year, self.view_month)

        # Clear existing grid items
        while self.grid_lay.count():
            item = self.grid_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cal = calendar.Calendar(firstweekday=0) # Monday first
        month_days = cal.monthdayscalendar(self.view_year, self.view_month)

        today = datetime.date.today()
        selected_str = self.selected_date.strftime("%Y-%m-%d")

        for row_idx, week in enumerate(month_days):
            for col_idx, day_num in enumerate(week):
                if day_num == 0:
                    # Empty cell (other month)
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
        self.setProperty("class", "ActionBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.current_date_str = initial_date_str if initial_date_str else datetime.date.today().strftime("%Y-%m-%d")
        self.clicked.connect(self._open_calendar_popup)
        self._update_button_label()

    def set_date_str(self, date_str: str):
        self.current_date_str = date_str
        self._update_button_label()

    def _update_button_label(self):
        try:
            d = datetime.datetime.strptime(self.current_date_str, "%Y-%m-%d").date()
            today = datetime.date.today()
            if d == today:
                formatted = f"📅 Today ({d.strftime('%b %d')}) ▾"
            else:
                formatted = f"📅 {d.strftime('%b %d, %Y')} ▾"
        except Exception:
            formatted = f"📅 {self.current_date_str} ▾"

        self.setText(formatted)

    def _open_calendar_popup(self):
        popup = GlowingCalendarPopup(self.current_date_str, self)
        popup.dateSelected.connect(self._on_popup_date_selected)
        
        # Position popup directly below the button
        btn_pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        popup.move(btn_pos)
        popup.exec()

    def _on_popup_date_selected(self, date_str: str):
        self.set_date_str(date_str)
        self.dateChanged.emit(date_str)

from typing import Dict, Any, Callable, List, Optional
from datetime import datetime
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QProgressBar, QToolTip, QSizePolicy
)
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush, QLinearGradient
from qhealth_core.db import set_app_budget
from ..utils import format_duration, format_number, get_app_icon_pixmap

RANGE_LABELS = {
    "day": "TODAY",
    "week": "LAST 7 DAYS",
    "month": "LAST 30 DAYS",
    "year": "THIS YEAR",
    "all_time": "ALL TIME"
}

TREND_TITLES = {
    "day": "24-HOUR USAGE TIMELINE",
    "week": "7-DAY USAGE TREND",
    "month": "30-DAY USAGE TREND",
    "year": "MONTHLY USAGE DISTRIBUTION",
    "all_time": "ALL-TIME MONTHLY TREND"
}

BUDGET_PRESETS = [
    (0, "No Limit"),
    (30, "30 Minutes / Day"),
    (60, "1 Hour / Day"),
    (90, "1.5 Hours / Day"),
    (120, "2 Hours / Day"),
    (180, "3 Hours / Day"),
    (240, "4 Hours / Day"),
    (300, "5 Hours / Day")
]

class AppTrendBarsPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(130)
        self.timeline: List[Dict[str, Any]] = []
        self.range_type = "day"
        self.setMouseTracking(True)
        self.bar_rects = []

    def set_data(self, timeline: List[Dict[str, Any]], range_type: str = "day"):
        self.timeline = timeline
        self.range_type = range_type
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        for rect, d, lbl in self.bar_rects:
            if rect.contains(pos.x(), pos.y()):
                dur = d.get("duration", 0)
                keys = d.get("keystrokes", 0)
                clicks = d.get("clicks", 0)
                tip = f"{lbl}\n⏱ Active: {format_duration(dur)}\n⌨ Keys: {format_number(keys)} · 🖱 Clicks: {format_number(clicks)}"
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self.bar_rects = []
        w = float(self.width())
        h = float(self.height()) - 22.0

        if not self.timeline:
            painter.end()
            return

        count = len(self.timeline)
        col_w = w / float(count)
        bar_w = max(3.0, min(32.0, col_w - 4.0))

        max_dur = max([d.get("duration", 0) for d in self.timeline] + [1])
        if self.range_type == "day":
            max_dur = max(3600.0, float(max_dur))

        current_hour = datetime.now().hour

        for i, item in enumerate(self.timeline):
            dur = item.get("duration", 0)
            x = i * col_w + (col_w - bar_w) / 2.0
            pct = min(1.0, max(0.04, dur / float(max_dur)))
            bar_h = pct * (h - 10)
            y = h - bar_h

            rect = QRectF(x, y, bar_w, bar_h)

            if self.range_type == "day":
                h_int = item.get("hour_int", i)
                lbl_text = f"🕒 {h_int:02d}:00"
                is_highlight = (h_int == current_hour)
            elif self.range_type in ("week", "month"):
                lbl_text = f"📅 {item.get('date', '')} ({item.get('label', '')})"
                is_highlight = (i == count - 1)
            else:
                lbl_text = f"📅 {item.get('month_str', '')}"
                is_highlight = (i == count - 1)

            self.bar_rects.append((rect, item, lbl_text))

            if dur > 0 and is_highlight:
                grad = QLinearGradient(x, y, x, h)
                grad.setColorAt(0, QColor("#34d399"))
                grad.setColorAt(1, QColor("#06b6d4"))
                painter.setBrush(QBrush(grad))
            elif dur > 0:
                painter.setBrush(QColor(16, 185, 129, 140))
            else:
                painter.setBrush(QColor(30, 41, 59, 80))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 3.0, 3.0)

        # X-axis labels
        painter.setPen(QColor("#64748b"))
        font = QFont("monospace", 8)
        painter.setFont(font)

        if self.range_type == "day":
            labels = [(0, "00:00"), (4, "04:00"), (8, "08:00"), (12, "12:00"), (16, "16:00"), (20, "20:00"), (23, "23:00")]
            for hour, txt in labels:
                lx = hour * col_w
                painter.drawText(QRectF(lx - 10, h + 4, 40, 16), Qt.AlignmentFlag.AlignCenter, txt)
        elif self.range_type == "week":
            for i, item in enumerate(self.timeline):
                lx = i * col_w
                painter.drawText(QRectF(lx - 6, h + 4, col_w + 12, 16), Qt.AlignmentFlag.AlignCenter, item.get("label", ""))
        elif self.range_type == "month":
            for i, item in enumerate(self.timeline):
                if i % 5 == 0 or i == count - 1:
                    lx = i * col_w
                    d_str = item.get("date", "")[-2:]
                    painter.drawText(QRectF(lx - 10, h + 4, 30, 16), Qt.AlignmentFlag.AlignCenter, d_str)
        else:
            for i, item in enumerate(self.timeline):
                lx = i * col_w
                m_label = item.get("label", item.get("month_str", "")[-2:])
                painter.drawText(QRectF(lx - 10, h + 4, col_w + 20, 16), Qt.AlignmentFlag.AlignCenter, m_label)

        painter.end()


class AppDetailView(QWidget):
    def __init__(self, on_back: Callable[[], None], parent=None):
        super().__init__(parent)
        self.on_back = on_back
        self.current_app_id = ""
        self._is_updating = False

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(12)

        # 1. Back Button Bar
        back_bar = QHBoxLayout()
        self.btn_back = QPushButton("← Back to Applications")
        self.btn_back.setProperty("class", "ActionBtn")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.on_back)
        back_bar.addWidget(self.btn_back)
        back_bar.addStretch()
        main_lay.addLayout(back_bar)

        # 2. Hero Header Card
        self.hero_card = QFrame()
        self.hero_card.setProperty("class", "GlassCard")
        hero_lay = QHBoxLayout(self.hero_card)
        hero_lay.setContentsMargins(18, 14, 18, 14)
        hero_lay.setSpacing(16)

        self.app_icon = QLabel()
        self.app_icon.setFixedSize(50, 50)
        self.app_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_lay.addWidget(self.app_icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.name_lbl = QLabel("Application")
        self.name_lbl.setStyleSheet("font-size: 19px; font-weight: 800; color: #ffffff;")

        self.id_lbl = QLabel("app.id")
        self.id_lbl.setStyleSheet("font-size: 11px; color: #64748b; font-family: monospace;")

        title_box.addWidget(self.name_lbl)
        title_box.addWidget(self.id_lbl)
        hero_lay.addLayout(title_box, 1)

        # Right total duration badge
        dur_box = QVBoxLayout()
        dur_box.setSpacing(2)
        dur_box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.range_tag_lbl = QLabel("SCREEN TIME (TODAY)")
        self.range_tag_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.8px;")
        self.total_dur_lbl = QLabel("0h 0m")
        self.total_dur_lbl.setStyleSheet("font-size: 22px; font-weight: 900; color: #34d399; font-family: monospace;")
        dur_box.addWidget(self.range_tag_lbl)
        dur_box.addWidget(self.total_dur_lbl)
        hero_lay.addLayout(dur_box)

        main_lay.addWidget(self.hero_card)

        # 3. Daily Usage Budget Card (Feature A)
        self.budget_card = QFrame()
        self.budget_card.setProperty("class", "GlassCard")
        b_lay = QVBoxLayout(self.budget_card)
        b_lay.setContentsMargins(18, 12, 18, 12)
        b_lay.setSpacing(8)

        b_top = QHBoxLayout()
        b_title = QLabel("DAILY TIME LIMIT & GOAL")
        b_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.6px;")
        b_top.addWidget(b_title)
        b_top.addStretch()

        self.budget_combo = QComboBox()
        for mins, label in BUDGET_PRESETS:
            self.budget_combo.addItem(label, mins)
        self.budget_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.budget_combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(30, 41, 59, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 3px 10px;
                color: #f8fafc;
                font-size: 11px;
                font-weight: 600;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #ffffff;
                selection-background-color: rgba(16, 185, 129, 0.3);
            }
        """)
        self.budget_combo.currentIndexChanged.connect(self._on_budget_changed)
        b_top.addWidget(self.budget_combo)
        b_lay.addLayout(b_top)

        # Progress bar for budget
        self.budget_progress_box = QVBoxLayout()
        self.budget_progress_box.setSpacing(3)
        self.budget_status_lbl = QLabel("No daily limit set")
        self.budget_status_lbl.setStyleSheet("font-size: 11px; color: #64748b; font-family: monospace;")
        
        self.budget_bar = QProgressBar()
        self.budget_bar.setFixedHeight(6)
        self.budget_bar.setTextVisible(False)
        self.budget_bar.setMaximum(100)
        self.budget_bar.setValue(0)
        self.budget_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(30, 41, 59, 0.6);
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #34d399;
                border-radius: 3px;
            }
        """)
        self.budget_progress_box.addWidget(self.budget_status_lbl)
        self.budget_progress_box.addWidget(self.budget_bar)
        b_lay.addLayout(self.budget_progress_box)

        main_lay.addWidget(self.budget_card)

        # 4. Stats Row (Keys, Clicks, Active Days)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)

        self.card_keys = QFrame()
        self.card_keys.setProperty("class", "GlassCard")
        k_lay = QVBoxLayout(self.card_keys)
        k_lay.setContentsMargins(14, 10, 14, 10)
        k_lbl = QLabel("KEYSTROKES IN RANGE")
        k_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        k_lay.addWidget(k_lbl)
        self.val_keys = QLabel("0")
        self.val_keys.setStyleSheet("font-size: 18px; font-weight: 800; color: #34d399; font-family: monospace;")
        k_lay.addWidget(self.val_keys)
        stats_row.addWidget(self.card_keys)

        self.card_clicks = QFrame()
        self.card_clicks.setProperty("class", "GlassCard")
        c_lay = QVBoxLayout(self.card_clicks)
        c_lay.setContentsMargins(14, 10, 14, 10)
        c_lbl = QLabel("CLICKS IN RANGE")
        c_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        c_lay.addWidget(c_lbl)
        self.val_clicks = QLabel("0")
        self.val_clicks.setStyleSheet("font-size: 18px; font-weight: 800; color: #22d3ee; font-family: monospace;")
        c_lay.addWidget(self.val_clicks)
        stats_row.addWidget(self.card_clicks)

        self.card_days = QFrame()
        self.card_days.setProperty("class", "GlassCard")
        d_lay = QVBoxLayout(self.card_days)
        d_lay.setContentsMargins(14, 10, 14, 10)
        d_lbl = QLabel("ACTIVE DAYS IN RANGE")
        d_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        d_lay.addWidget(d_lbl)
        self.val_days = QLabel("0 days")
        self.val_days.setStyleSheet("font-size: 18px; font-weight: 800; color: #818cf8; font-family: monospace;")
        d_lay.addWidget(self.val_days)
        stats_row.addWidget(self.card_days)

        main_lay.addLayout(stats_row)

        # 5. Usage Trend
        trend_card = QFrame()
        trend_card.setProperty("class", "GlassCard")
        tr_lay = QVBoxLayout(trend_card)
        tr_lay.setContentsMargins(18, 14, 18, 14)
        tr_lay.setSpacing(8)
        self.trend_title_lbl = QLabel("USAGE TREND")
        self.trend_title_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        tr_lay.addWidget(self.trend_title_lbl)
        self.trend_painter = AppTrendBarsPainter(trend_card)
        tr_lay.addWidget(self.trend_painter)
        main_lay.addWidget(trend_card)

        # 6. Recent Window Titles
        self.titles_card = QFrame()
        self.titles_card.setProperty("class", "GlassCard")
        self.titles_lay = QVBoxLayout(self.titles_card)
        self.titles_lay.setContentsMargins(18, 14, 18, 14)
        self.titles_lay.setSpacing(6)
        t_hdr = QLabel("RECENT WINDOW TITLES & TASKS")
        t_hdr.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        self.titles_lay.addWidget(t_hdr)
        self.titles_box = QVBoxLayout()
        self.titles_box.setSpacing(4)
        self.titles_lay.addLayout(self.titles_box)
        main_lay.addWidget(self.titles_card)

    def _on_budget_changed(self, idx: int):
        if self._is_updating or not self.current_app_id:
            return
        limit_mins = self.budget_combo.currentData()
        set_app_budget(self.current_app_id, limit_mins, enabled=(limit_mins > 0))

    def set_app_data(self, data: Dict[str, Any], range_type: str = "day"):
        app_name = data.get("display_name", "Unknown")
        icon_name = data.get("icon", "")
        app_id = data.get("app_id", "")
        self.current_app_id = app_id

        self.name_lbl.setText(app_name)
        self.id_lbl.setText(f"({app_id})")
        self.app_icon.setPixmap(get_app_icon_pixmap(icon_name, app_name, 50))

        # Dynamic Range Labels
        r_tag = RANGE_LABELS.get(range_type, "CUSTOM")
        self.range_tag_lbl.setText(f"SCREEN TIME ({r_tag})")
        self.trend_title_lbl.setText(TREND_TITLES.get(range_type, "USAGE TREND"))

        dur = data.get("total_duration", 0)
        self.total_dur_lbl.setText(format_duration(dur))
        self.val_keys.setText(format_number(data.get("total_keystrokes", 0)))
        self.val_clicks.setText(format_number(data.get("total_clicks", 0)))
        self.val_days.setText(f"{data.get('active_days', 0)} days")

        # Update budget section
        self._is_updating = True
        budget_info = data.get("budget") or {}
        limit_mins = budget_info.get("daily_limit_minutes", 0) if budget_info.get("enabled", 1) else 0
        
        idx = self.budget_combo.findData(limit_mins)
        if idx >= 0:
            self.budget_combo.setCurrentIndex(idx)
        else:
            self.budget_combo.setCurrentIndex(0)
        self._is_updating = False

        if limit_mins > 0:
            limit_secs = limit_mins * 60
            pct = min(100, int((dur / float(limit_secs)) * 100))
            self.budget_bar.setValue(pct)
            
            bar_color = "#34d399" if pct < 80 else ("#fbbf24" if pct < 100 else "#f87171")
            self.budget_bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: rgba(30, 41, 59, 0.6);
                    border: none;
                    border-radius: 3px;
                }}
                QProgressBar::chunk {{
                    background-color: {bar_color};
                    border-radius: 3px;
                }}
            """)
            self.budget_status_lbl.setText(f"Usage today: {format_duration(dur)} / {format_duration(limit_secs)} ({pct}%)")
        else:
            self.budget_bar.setValue(0)
            self.budget_status_lbl.setText("No daily budget set for this app.")

        # Trend bars
        self.trend_painter.set_data(data.get("timeline", []), range_type)

        # Recent titles
        while self.titles_box.count():
            item = self.titles_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        titles = data.get("recent_titles", [])
        if not titles:
            lbl = QLabel("No window titles logged in this time range")
            lbl.setStyleSheet("color: #64748b; font-size: 11px; font-style: italic; padding: 4px;")
            self.titles_box.addWidget(lbl)
        else:
            for t in titles[:6]:
                row = QFrame()
                row.setProperty("class", "GlassCardInner")
                r_lay = QHBoxLayout(row)
                r_lay.setContentsMargins(10, 5, 10, 5)
                t_lbl = QLabel(t)
                t_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px; font-family: monospace;")
                r_lay.addWidget(t_lbl)
                self.titles_box.addWidget(row)

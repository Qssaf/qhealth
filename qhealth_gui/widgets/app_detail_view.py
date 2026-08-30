from typing import Dict, Any, Callable
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea
)
from PyQt6.QtGui import QPainter, QColor, QFont, QBrush, QLinearGradient
from ..utils import format_duration, format_number, get_category_color, get_app_icon_pixmap

class AppTrendBarsPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(140)
        self.history = []

    def set_data(self, history):
        self.history = history
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height() - 24

        if not self.history:
            painter.end()
            return

        max_dur = max([d.get("duration", 0) for d in self.history] + [1])
        count = len(self.history)
        col_w = w / float(count)
        bar_w = min(32.0, col_w - 8.0)

        for i, d in enumerate(self.history):
            dur = d.get("duration", 0)
            day_name = d.get("day_name", "")
            date_str = d.get("date", "")
            is_today = (i == count - 1)

            pct = max(0.06, dur / float(max_dur))
            bar_h = pct * (h - 20)
            x = i * col_w + (col_w - bar_w) / 2.0
            y = h - bar_h

            rect = QRectF(x, y, bar_w, bar_h)

            if is_today:
                grad = QLinearGradient(x, y, x, h)
                grad.setColorAt(0, QColor("#34d399"))
                grad.setColorAt(1, QColor("#06b6d4"))
                painter.setBrush(QBrush(grad))
            elif dur > 0:
                painter.setBrush(QColor(16, 185, 129, 140))
            else:
                painter.setBrush(QColor(30, 41, 59, 90))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 4, 4)

            # Date label below
            painter.setPen(QColor("#64748b"))
            font = QFont("monospace", 7)
            painter.setFont(font)
            painter.drawText(QRectF(x - 10, h + 4, bar_w + 20, 14), Qt.AlignmentFlag.AlignCenter, date_str[-5:])

        painter.end()


class AppDetailView(QWidget):
    def __init__(self, on_back: Callable[[], None], parent=None):
        super().__init__(parent)
        self.on_back = on_back

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(14)

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
        hero_lay.setContentsMargins(18, 16, 18, 16)
        hero_lay.setSpacing(16)

        self.app_icon = QLabel()
        self.app_icon.setFixedSize(54, 54)
        self.app_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_lay.addWidget(self.app_icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        self.name_lbl = QLabel("Application")
        self.name_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #ffffff;")

        sub_row = QHBoxLayout()
        sub_row.setSpacing(8)
        self.cat_lbl = QLabel("Category")
        self.cat_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #34d399; font-family: monospace;")
        self.id_lbl = QLabel("app.id")
        self.id_lbl.setStyleSheet("font-size: 11px; color: #64748b; font-family: monospace;")
        sub_row.addWidget(self.cat_lbl)
        sub_row.addWidget(self.id_lbl)
        sub_row.addStretch()

        title_box.addWidget(self.name_lbl)
        title_box.addLayout(sub_row)
        hero_lay.addLayout(title_box, 1)

        # Right total duration badge
        dur_box = QVBoxLayout()
        dur_box.setSpacing(2)
        dur_box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        t_title = QLabel("TOTAL SCREEN TIME")
        t_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.8px;")
        self.total_dur_lbl = QLabel("0h 0m")
        self.total_dur_lbl.setStyleSheet("font-size: 24px; font-weight: 900; color: #34d399; font-family: monospace;")
        dur_box.addWidget(t_title)
        dur_box.addWidget(self.total_dur_lbl)
        hero_lay.addLayout(dur_box)

        main_lay.addWidget(self.hero_card)

        # 3. Stats Row (Keys, Clicks, Active Days)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)

        self.card_keys = QFrame()
        self.card_keys.setProperty("class", "GlassCard")
        k_lay = QVBoxLayout(self.card_keys)
        k_lay.setContentsMargins(14, 10, 14, 10)
        k_lay.addWidget(QLabel("TOTAL KEYSTROKES"))
        self.val_keys = QLabel("0")
        self.val_keys.setStyleSheet("font-size: 18px; font-weight: 800; color: #34d399; font-family: monospace;")
        k_lay.addWidget(self.val_keys)
        stats_row.addWidget(self.card_keys)

        self.card_clicks = QFrame()
        self.card_clicks.setProperty("class", "GlassCard")
        c_lay = QVBoxLayout(self.card_clicks)
        c_lay.setContentsMargins(14, 10, 14, 10)
        c_lay.addWidget(QLabel("TOTAL CLICKS"))
        self.val_clicks = QLabel("0")
        self.val_clicks.setStyleSheet("font-size: 18px; font-weight: 800; color: #22d3ee; font-family: monospace;")
        c_lay.addWidget(self.val_clicks)
        stats_row.addWidget(self.card_clicks)

        self.card_days = QFrame()
        self.card_days.setProperty("class", "GlassCard")
        d_lay = QVBoxLayout(self.card_days)
        d_lay.setContentsMargins(14, 10, 14, 10)
        d_lay.addWidget(QLabel("ACTIVE DAYS"))
        self.val_days = QLabel("0 days")
        self.val_days.setStyleSheet("font-size: 18px; font-weight: 800; color: #818cf8; font-family: monospace;")
        d_lay.addWidget(self.val_days)
        stats_row.addWidget(self.card_days)

        main_lay.addLayout(stats_row)

        # 4. 14-Day Usage Trend
        trend_card = QFrame()
        trend_card.setProperty("class", "GlassCard")
        tr_lay = QVBoxLayout(trend_card)
        tr_lay.setContentsMargins(18, 14, 18, 14)
        tr_lay.setSpacing(8)
        tr_lay.addWidget(QLabel("14-DAY USAGE TREND"))
        self.trend_painter = AppTrendBarsPainter(trend_card)
        tr_lay.addWidget(self.trend_painter)
        main_lay.addWidget(trend_card)

        # 5. Recent Window Titles
        self.titles_card = QFrame()
        self.titles_card.setProperty("class", "GlassCard")
        self.titles_lay = QVBoxLayout(self.titles_card)
        self.titles_lay.setContentsMargins(18, 14, 18, 14)
        self.titles_lay.setSpacing(6)
        self.titles_lay.addWidget(QLabel("RECENT WINDOW TITLES"))
        self.titles_box = QVBoxLayout()
        self.titles_box.setSpacing(4)
        self.titles_lay.addLayout(self.titles_box)
        main_lay.addWidget(self.titles_card)

    def set_app_data(self, data: Dict[str, Any]):
        app_name = data.get("display_name", "Unknown")
        icon_name = data.get("icon", "")
        category = data.get("category", "Other")
        app_id = data.get("app_id", "")

        self.name_lbl.setText(app_name)
        self.cat_lbl.setText(category)
        self.id_lbl.setText(f"({app_id})")
        self.app_icon.setPixmap(get_app_icon_pixmap(icon_name, app_name, 54))

        dur = data.get("total_duration", 0)
        self.total_dur_lbl.setText(format_duration(dur))
        self.val_keys.setText(format_number(data.get("total_keystrokes", 0)))
        self.val_clicks.setText(format_number(data.get("total_clicks", 0)))
        self.val_days.setText(f"{data.get('active_days', 0)} days")

        # Trend bars
        self.trend_painter.set_data(data.get("daily_history", []))

        # Recent titles
        while self.titles_box.count():
            item = self.titles_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        titles = data.get("recent_titles", [])
        if not titles:
            lbl = QLabel("No window titles logged")
            lbl.setStyleSheet("color: #64748b; font-size: 11px; font-style: italic;")
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

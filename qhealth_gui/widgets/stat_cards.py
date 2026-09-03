from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel
from ..utils import format_number, format_duration

class StatCard(QFrame):
    def __init__(self, title: str, accent_color: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(3)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.8px;")

        self.val_lbl = QLabel("0")
        self.val_lbl.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {accent_color}; font-family: monospace;")

        self.sub_lbl = QLabel("Stats")
        self.sub_lbl.setStyleSheet("font-size: 10px; color: #64748b;")

        lay.addWidget(t_lbl)
        lay.addWidget(self.val_lbl)
        lay.addWidget(self.sub_lbl)

    def set_value(self, val: str, sub: str = ""):
        self.val_lbl.setText(val)
        if sub:
            self.sub_lbl.setText(sub)


class StatCardsWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self.card_time = StatCard("ACTIVE SCREEN TIME", "#34d399")
        self.card_keys = StatCard("KEYSTROKES", "#22d3ee")
        self.card_clicks = StatCard("CLICKS & SCROLLS", "#818cf8")
        self.card_top = StatCard("TOP APP", "#fbbf24")

        lay.addWidget(self.card_time)
        lay.addWidget(self.card_keys)
        lay.addWidget(self.card_clicks)
        lay.addWidget(self.card_top)

    def update_stats(self, total_seconds: int, keys: int, clicks: int, scrolls: int, top_app_name: str, top_app_pct: float, focus_score: int = 100, focus_rating: str = "Deep Work"):
        time_sub = f"Focus: {focus_rating} ({focus_score}%)" if total_seconds > 0 else "Foreground app time"
        self.card_time.set_value(format_duration(total_seconds), time_sub)
        self.card_keys.set_value(format_number(keys), "Recorded keypresses")
        self.card_clicks.set_value(f"{format_number(clicks)}", f"{format_number(scrolls)} scrolls")

        if top_app_name:
            self.card_top.set_value(top_app_name, f"{top_app_pct}% of total")
        else:
            self.card_top.set_value("—", "No activity recorded")

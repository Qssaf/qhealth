from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QSizePolicy
from .. import theme as t
from ..utils import format_number, format_duration


class StatCard(QFrame):
    """KPI tile: metric identity dot + label, the number in primary ink, one line of context."""

    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent)
        self.setProperty("class", "Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(t.PAD, 14, t.PAD, 14)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        hdr.setSpacing(7)
        hdr.addWidget(t.dot(color))
        hdr.addWidget(t.label(title, "overline"))
        hdr.addStretch()
        lay.addLayout(hdr)

        self.val_lbl = t.label("0", "metric")
        lay.addWidget(self.val_lbl)
        self.sub_lbl = t.label("", "caption")
        lay.addWidget(self.sub_lbl)
        # Separate badge label: Qt won't re-apply padding when a label's role flips at runtime
        self.badge_lbl = t.label("", "badge")
        self.badge_lbl.hide()
        lay.addWidget(self.badge_lbl, 0, Qt.AlignmentFlag.AlignLeft)

    def set_value(self, val: str, sub: str = "", tone: str = ""):
        """`tone` ("good" / "warn" / "bad") turns the context line into a status badge."""
        self.val_lbl.setText(val)
        if sub:
            self.sub_lbl.setText(sub)
            self.badge_lbl.setText(sub)
        self.sub_lbl.setVisible(not tone)
        self.badge_lbl.setVisible(bool(tone))
        t.set_prop(self.badge_lbl, "tone", tone)


class StatCardsWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(t.GAP)

        self.card_time = StatCard("SCREEN TIME", t.SERIES_TIME)
        self.card_keys = StatCard("KEYSTROKES", t.SERIES_KEYS)
        self.card_clicks = StatCard("CLICKS", t.SERIES_CLICKS)
        self.card_top = StatCard("TOP APP", t.TEXT_3)
        self.cards = [self.card_time, self.card_keys, self.card_clicks, self.card_top]
        self.columns = 0
        self.set_columns(4)

    def set_columns(self, columns: int):
        """4 across on wide windows, 2x2 when narrow."""
        if columns == self.columns:
            return
        self.columns = columns
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // columns, i % columns)
        for c in range(4):
            self.grid.setColumnStretch(c, 1 if c < columns else 0)

    def update_stats(self, total_seconds: int, keys: int, clicks: int, scrolls: int, top_app_name: str, top_app_pct: float, focus_score: int = 100, focus_rating: str = "Deep Work"):
        if total_seconds > 0:
            tone = "good" if focus_score >= 80 else ("warn" if focus_score >= 60 else "bad")
            self.card_time.set_value(format_duration(total_seconds), f"{focus_rating} · {focus_score}% focus", tone)
        else:
            self.card_time.set_value("0h 0m", "No foreground time yet")

        self.card_keys.set_value(format_number(keys), "Key presses")
        self.card_clicks.set_value(format_number(clicks), f"{format_number(scrolls)} scrolls")

        if top_app_name:
            disp_app = top_app_name if len(top_app_name) <= 16 else top_app_name[:14] + "…"
            self.card_top.set_value(disp_app, f"{top_app_pct}% of screen time")
            self.card_top.val_lbl.setToolTip(top_app_name)
        else:
            self.card_top.set_value("—", "No activity recorded")
            self.card_top.val_lbl.setToolTip("")

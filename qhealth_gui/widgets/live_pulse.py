from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QSizePolicy
from .. import theme as t
from ..icons import pixmap
from ..utils import get_app_icon_pixmap

STATUS = {  # state -> (badge text, tone)
    "waiting": ("● Waiting for data", ""),
    "live": ("● Live", "good"),
    "idle": ("● Idle", ""),
    "paused": ("● Paused", "warn"),
    "no_input": ("● No input access", "bad"),
}


class LivePulseWidget(QFrame):
    """'Now' strip: the focused app and window plus live typing / clicking speed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.current_app_id = ""

        lay = QHBoxLayout(self)
        lay.setContentsMargins(t.PAD, 14, t.PAD, 14)
        lay.setSpacing(14)

        icon_tile = QFrame()
        icon_tile.setProperty("class", "Tile")
        icon_tile.setFixedSize(48, 48)
        i_lay = QVBoxLayout(icon_tile)
        i_lay.setContentsMargins(0, 0, 0, 0)
        self.app_icon_lbl = t.label("", "body")
        self.app_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.app_icon_lbl.setPixmap(pixmap("overview", t.TEXT_3, 24))
        i_lay.addWidget(self.app_icon_lbl)
        lay.addWidget(icon_tile)

        info = QVBoxLayout()
        info.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(t.label("NOW ACTIVE", "overline"))
        self.badge = t.label("", "badge")
        top.addWidget(self.badge)
        top.addStretch()
        info.addLayout(top)

        self.app_name_lbl = t.label("Desktop / Idle", "h2")
        self.title_lbl = t.label("No active foreground window", "caption")
        self.title_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addWidget(self.app_name_lbl)
        info.addWidget(self.title_lbl)
        lay.addLayout(info, 1)

        self.wpm_card, self.wpm_val = self._metric("WPM", "Typing speed", t.SERIES_KEYS)
        self.cpm_card, self.cpm_val = self._metric("CPM", "Clicks per minute", t.SERIES_CLICKS)
        lay.addWidget(self.wpm_card)
        lay.addWidget(self.cpm_card)
        self._set_status("waiting")

    def _metric(self, name: str, caption: str, color: str):
        tile = QFrame()
        tile.setProperty("class", "Tile")
        tile.setMinimumWidth(128)
        v = QVBoxLayout(tile)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(0)
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(t.dot(color, 6))
        head.addWidget(t.label(name, "overline"))
        head.addStretch()
        v.addLayout(head)
        val = t.label("0", "live")
        val.setAccessibleName(caption)
        v.addWidget(val)
        v.addWidget(t.label(caption, "caption"))
        return tile, val

    def _set_status(self, state: str):
        text, tone = STATUS[state]
        self.badge.setText(text)
        t.set_prop(self.badge, "tone", tone)

    def update_metrics(self, data: dict):
        if not data:
            return

        no_input = data.get("input_access_denied", False)
        # Explain why nothing is being recorded; cleared as soon as access works
        self.badge.setToolTip(
            "QHealth cannot read /dev/input, so no activity is recorded.\n"
            "Fix: sudo usermod -aG input $USER, then log out and back in." if no_input else ""
        )
        if data.get("is_paused", False):
            self._set_status("paused")
        elif no_input:
            self._set_status("no_input")
        elif data.get("is_idle", False):
            self._set_status("idle")
        else:
            self._set_status("live")

        app = data.get("active_app", "Desktop")
        self.current_app_id = data.get("app_id", "")
        self.app_name_lbl.setText(app if app else "Desktop")
        self.app_icon_lbl.setPixmap(get_app_icon_pixmap(data.get("app_icon", ""), app, 32))

        raw_title = data.get("active_title", "")
        disp_title = raw_title if len(raw_title) <= 90 else raw_title[:87] + "…"
        self.title_lbl.setText(disp_title if disp_title else "No active window title")
        self.title_lbl.setToolTip(raw_title if raw_title else "")

        self.wpm_val.setText(str(data.get("live_wpm", 0)))
        self.cpm_val.setText(str(data.get("live_cpm", 0)))

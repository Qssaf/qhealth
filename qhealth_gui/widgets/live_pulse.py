from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel
from ..utils import get_app_icon_pixmap

class LivePulseWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")

        main_lay = QHBoxLayout(self)
        main_lay.setContentsMargins(18, 14, 18, 14)
        main_lay.setSpacing(16)

        # Left: App Icon + Details
        left_box = QHBoxLayout()
        left_box.setSpacing(14)

        self.app_icon_lbl = QLabel()
        self.app_icon_lbl.setFixedSize(42, 42)
        self.app_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.app_icon_lbl.setPixmap(get_app_icon_pixmap("user-desktop", "Desktop", 42))

        info_box = QVBoxLayout()
        info_box.setSpacing(2)

        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(8)

        status_lbl = QLabel("CURRENT FOCUS")
        status_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.8px;")

        self.badge = QLabel("LIVE")
        self.badge.setStyleSheet("font-size: 9px; font-weight: 700; color: #34d399; background-color: rgba(16,185,129,0.15); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(16,185,129,0.3);")

        hdr_row.addWidget(status_lbl)
        hdr_row.addWidget(self.badge)
        hdr_row.addStretch()
        info_box.addLayout(hdr_row)

        self.app_name_lbl = QLabel("Desktop / Idle")
        self.app_name_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")

        self.title_lbl = QLabel("No active foreground window")
        self.title_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        self.title_lbl.setMaximumWidth(450)

        info_box.addWidget(self.app_name_lbl)
        info_box.addWidget(self.title_lbl)

        left_box.addWidget(self.app_icon_lbl)
        left_box.addLayout(info_box)

        main_lay.addLayout(left_box, 1)

        # Right: Live Speedometers (WPM, CPM)
        metrics_lay = QHBoxLayout()
        metrics_lay.setSpacing(10)

        # WPM (Typing Speed)
        self.wpm_card = QFrame()
        self.wpm_card.setProperty("class", "GlassCardInner")
        w_lay = QVBoxLayout(self.wpm_card)
        w_lay.setContentsMargins(16, 8, 16, 8)
        w_lay.setSpacing(0)
        self.wpm_val = QLabel("0")
        self.wpm_val.setStyleSheet("font-size: 18px; font-weight: 800; color: #34d399; font-family: monospace;")
        self.wpm_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wpm_sub = QLabel("Typing (WPM)")
        wpm_sub.setStyleSheet("font-size: 9px; color: #64748b; font-weight: 600;")
        wpm_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w_lay.addWidget(self.wpm_val)
        w_lay.addWidget(wpm_sub)
        metrics_lay.addWidget(self.wpm_card)

        # CPM (Mouse Clicks / Min)
        self.cpm_card = QFrame()
        self.cpm_card.setProperty("class", "GlassCardInner")
        c_lay = QVBoxLayout(self.cpm_card)
        c_lay.setContentsMargins(16, 8, 16, 8)
        c_lay.setSpacing(0)
        self.cpm_val = QLabel("0")
        self.cpm_val.setStyleSheet("font-size: 18px; font-weight: 800; color: #22d3ee; font-family: monospace;")
        self.cpm_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cpm_sub = QLabel("Clicks / Min")
        cpm_sub.setStyleSheet("font-size: 9px; color: #64748b; font-weight: 600;")
        cpm_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_lay.addWidget(self.cpm_val)
        c_lay.addWidget(cpm_sub)
        metrics_lay.addWidget(self.cpm_card)

        main_lay.addLayout(metrics_lay)

    def update_metrics(self, data: dict):
        if not data:
            return

        is_paused = data.get("is_paused", False)
        is_idle = data.get("is_idle", False)

        if is_paused:
            self.badge.setText("PAUSED")
            self.badge.setStyleSheet("font-size: 9px; font-weight: 700; color: #fbbf24; background-color: rgba(245,158,11,0.15); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(245,158,11,0.3);")
        elif is_idle:
            self.badge.setText("IDLE / AFK")
            self.badge.setStyleSheet("font-size: 9px; font-weight: 700; color: #94a3b8; background-color: rgba(100,116,139,0.15); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(100,116,139,0.3);")
        else:
            self.badge.setText("LIVE")
            self.badge.setStyleSheet("font-size: 9px; font-weight: 700; color: #34d399; background-color: rgba(16,185,129,0.15); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(16,185,129,0.3);")

        app = data.get("active_app", "Desktop")
        icon_name = data.get("app_icon", "")
        self.app_name_lbl.setText(app if app else "Desktop")
        self.app_icon_lbl.setPixmap(get_app_icon_pixmap(icon_name, app, 42))

        title = data.get("active_title", "")
        if len(title) > 60:
            title = title[:57] + "..."
        self.title_lbl.setText(title if title else "No active window title")

        self.wpm_val.setText(str(data.get("live_wpm", 0)))
        self.cpm_val.setText(str(data.get("live_cpm", 0)))

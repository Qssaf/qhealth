from typing import List, Dict, Any, Callable, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QWidget, QProgressBar
)
from ..utils import format_duration, format_number, get_app_icon_pixmap, get_app_color

class AppRowWidget(QFrame):
    def __init__(self, app_data: Dict[str, Any], index: int = 0, on_click: Optional[Callable[[Dict[str, Any]], None]] = None, parent=None):
        super().__init__(parent)
        self.app_data = app_data
        self.on_click = on_click
        self.setProperty("class", "GlassCardInner")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(14)

        # Real Application Icon
        app_name = app_data.get("app_name", "Unknown")
        app_id = app_data.get("app_id", "")
        icon_name = app_data.get("icon", app_id)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(get_app_icon_pixmap(icon_name, app_name, 36))
        lay.addWidget(icon_lbl)

        # App Name & Subtitle
        name_box = QVBoxLayout()
        name_box.setSpacing(2)
        name_lbl = QLabel(app_name)
        name_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #ffffff;")

        id_lbl = QLabel(app_id if app_id else "application")
        id_lbl.setStyleSheet("font-size: 10px; color: #64748b; font-family: monospace;")

        name_box.addWidget(name_lbl)
        name_box.addWidget(id_lbl)
        lay.addLayout(name_box, 1)

        # Progress bar (percentage of screen time)
        pct = app_data.get("percentage", 0.0)
        app_color = get_app_color(app_name, index)

        p_box = QVBoxLayout()
        p_box.setSpacing(2)
        p_top = QHBoxLayout()
        p_title = QLabel("Share of active time")
        p_title.setStyleSheet("font-size: 10px; color: #64748b;")
        p_val = QLabel(f"{pct}%")
        p_val.setStyleSheet("font-size: 10px; font-weight: 700; color: #f8fafc; font-family: monospace;")
        p_top.addWidget(p_title)
        p_top.addStretch()
        p_top.addWidget(p_val)

        p_bar = QProgressBar()
        p_bar.setFixedHeight(5)
        p_bar.setTextVisible(False)
        p_bar.setMaximum(100)
        p_bar.setValue(int(pct))
        p_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(30, 41, 59, 0.6);
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {app_color.name()};
                border-radius: 2px;
            }}
        """)
        p_box.addLayout(p_top)
        p_box.addWidget(p_bar)
        lay.addLayout(p_box, 2)

        # Stats (Keys, Clicks, Duration)
        stats_box = QHBoxLayout()
        stats_box.setSpacing(16)

        keys_lbl = QLabel(f"⌨ {format_number(app_data.get('keystrokes', 0))}")
        keys_lbl.setStyleSheet("font-size: 11px; color: #94a3b8; font-family: monospace;")

        clicks_lbl = QLabel(f"🖱 {format_number(app_data.get('clicks', 0))}")
        clicks_lbl.setStyleSheet("font-size: 11px; color: #94a3b8; font-family: monospace;")

        dur = app_data.get("duration", 0)
        dur_lbl = QLabel(format_duration(dur))
        dur_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #34d399; font-family: monospace;")
        dur_lbl.setMinimumWidth(70)
        dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        stats_box.addWidget(keys_lbl)
        stats_box.addWidget(clicks_lbl)
        stats_box.addWidget(dur_lbl)
        lay.addLayout(stats_box)

        # Arrow indicator
        arr_lbl = QLabel("→")
        arr_lbl.setStyleSheet("color: #64748b; font-size: 14px; font-weight: 700; padding-left: 6px;")
        lay.addWidget(arr_lbl)

    def mousePressEvent(self, event):
        if self.on_click:
            self.on_click(self.app_data)
        super().mousePressEvent(event)


class AppLeaderboardWidget(QFrame):
    def __init__(self, on_app_click: Optional[Callable[[Dict[str, Any]], None]] = None, parent=None):
        super().__init__(parent)
        self.on_app_click = on_app_click
        self.setProperty("class", "GlassCard")

        self.apps: List[Dict[str, Any]] = []
        self.sort_by = "duration"
        self.search_text = ""

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(18, 16, 18, 16)
        main_lay.setSpacing(12)

        # Top Bar: Title + Search + Sort
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        t_lbl = QLabel("TRACKED APPLICATIONS")
        t_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        self.count_lbl = QLabel("0 applications tracked")
        self.count_lbl.setStyleSheet("font-size: 10px; color: #64748b; font-family: monospace;")
        title_box.addWidget(t_lbl)
        title_box.addWidget(self.count_lbl)
        top_bar.addLayout(title_box)

        top_bar.addStretch()

        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search apps...")
        self.search_input.setFixedWidth(170)
        self.search_input.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_input)

        # Sort Buttons
        sort_box = QHBoxLayout()
        sort_box.setSpacing(4)

        self.btn_time = QPushButton("Time")
        self.btn_time.setProperty("class", "ActionBtn")
        self.btn_time.setCheckable(True)
        self.btn_time.setChecked(True)
        self.btn_time.clicked.connect(lambda: self._set_sort("duration"))

        self.btn_keys = QPushButton("Keys")
        self.btn_keys.setProperty("class", "ActionBtn")
        self.btn_keys.setCheckable(True)
        self.btn_keys.clicked.connect(lambda: self._set_sort("keystrokes"))

        self.btn_clicks = QPushButton("Clicks")
        self.btn_clicks.setProperty("class", "ActionBtn")
        self.btn_clicks.setCheckable(True)
        self.btn_clicks.clicked.connect(lambda: self._set_sort("clicks"))

        sort_box.addWidget(self.btn_time)
        sort_box.addWidget(self.btn_keys)
        sort_box.addWidget(self.btn_clicks)
        top_bar.addLayout(sort_box)

        main_lay.addLayout(top_bar)

        # Scrollable App List Container
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 4, 0, 4)
        self.scroll_layout.setSpacing(8)
        self.scroll_area.setWidget(self.scroll_content)

        main_lay.addWidget(self.scroll_area)

    def _set_sort(self, mode: str):
        self.sort_by = mode
        self.btn_time.setChecked(mode == "duration")
        self.btn_keys.setChecked(mode == "keystrokes")
        self.btn_clicks.setChecked(mode == "clicks")
        self._refresh_list()

    def _on_search_changed(self, text: str):
        self.search_text = text.lower().strip()
        self._refresh_list()

    def update_apps(self, apps: List[Dict[str, Any]]):
        self.apps = apps
        self.count_lbl.setText(f"{len(apps)} application{'s' if len(apps) != 1 else ''} tracked")
        self._refresh_list()

    def _refresh_list(self):
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        filtered = [
            a for a in self.apps
            if not self.search_text or self.search_text in a.get("app_name", "").lower() or self.search_text in a.get("app_id", "").lower()
        ]

        filtered.sort(key=lambda x: x.get(self.sort_by, 0), reverse=True)

        if not filtered:
            empty_lbl = QLabel("No application activity recorded in this time range.")
            empty_lbl.setStyleSheet("color: #64748b; font-size: 12px; font-style: italic; padding: 30px;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.scroll_layout.addWidget(empty_lbl)
        else:
            for idx, app in enumerate(filtered):
                row = AppRowWidget(app, index=idx, on_click=self.on_app_click, parent=self.scroll_content)
                self.scroll_layout.addWidget(row)

        self.scroll_layout.addStretch()

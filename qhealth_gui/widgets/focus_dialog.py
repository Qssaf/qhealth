import time
import os
from typing import List, Dict, Any, Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QCheckBox, QLineEdit, QScrollArea, QWidget, QFrame,
    QSpinBox, QMessageBox, QSizePolicy, QProgressBar
)

from qhealth_core.db import (
    get_focus_session, start_focus_session, stop_focus_session,
    get_stats_by_range
)
from qhealth_core.app_resolver import app_resolver
from qhealth_core.blocker import is_immune, force_close_app, running_gui_apps
from qhealth_core.paths import IS_WINDOWS
from .. import theme as t
from ..icons import icon, pixmap
from ..utils import get_app_icon_pixmap, category_badge_html


def _is_allowed(candidates, allowed_set) -> bool:
    for cand in candidates:
        if not cand:
            continue
        if cand in allowed_set:
            return True
        for a_id in allowed_set:
            if (cand == a_id or cand.endswith(f".{a_id}") or
                a_id.endswith(f".{cand}") or cand.startswith(f"{a_id}-") or
                a_id.startswith(f"{cand}-") or cand.startswith(f"{a_id}_") or
                a_id.startswith(f"{cand}_")):
                return True
    return False


def terminate_unallowed_apps_on_start(allowed_apps: List[str]):
    """Force closes any running non-immune GUI application that is not in the allowlist."""
    allowed_set = {a.lower().strip() for a in allowed_apps if a}

    if IS_WINDOWS:
        for pid, name in running_gui_apps():
            if pid != os.getpid() and not is_immune(name, "", pid) and not _is_allowed((name,), allowed_set):
                force_close_app(name, name, pid)
        return

    uid = os.getuid()
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            p = int(entry)
            if is_immune("", "", p):
                continue
            try:
                stat = os.stat(f"/proc/{p}")
                if stat.st_uid != uid:
                    continue

                comm = ""
                with open(f"/proc/{p}/comm", "r") as cf:
                    comm = cf.read().strip().lower()

                cmdline = ""
                with open(f"/proc/{p}/cmdline", "rb") as cmdf:
                    cmdline = cmdf.read().decode("utf-8", errors="ignore").lower()

                exec_path = cmdline.split("\x00")[0] if cmdline else ""
                exec_base = os.path.basename(exec_path) if exec_path else ""

                if is_immune(comm, exec_base, p):
                    continue

                if not _is_allowed((comm, exec_base), allowed_set):
                    if comm in app_resolver._apps_cache or exec_base in app_resolver._apps_cache:
                        force_close_app(comm, comm, p)
            except Exception:
                pass
    except Exception:
        pass


class FocusAppItem(QFrame):
    """An app row in the allowlist picker: checkbox, native icon, name, category. Whole row toggles."""
    toggled = pyqtSignal(bool)

    def __init__(self, app_id: str, app_name: str, icon_name: str, category: str, parent=None):
        super().__init__(parent)
        self.app_id = app_id.lower().strip()
        self.app_name = app_name
        self.category = category

        self.setProperty("class", "Row")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(12)

        self.checkbox = QCheckBox()
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.setAccessibleName(f"Allow {app_name}")
        self.checkbox.stateChanged.connect(self._on_check_changed)
        lay.addWidget(self.checkbox)

        icon_lbl = t.label()
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(get_app_icon_pixmap(icon_name, app_name, 28))
        lay.addWidget(icon_lbl)

        info_box = QVBoxLayout()
        info_box.setSpacing(0)
        name_lbl = t.label(app_name if len(app_name) <= 26 else app_name[:24] + "…", "h3")
        name_lbl.setToolTip(app_name)
        id_lbl = t.label(self.app_id if len(self.app_id) <= 30 else self.app_id[:28] + "…", "caption")
        id_lbl.setToolTip(self.app_id)
        info_box.addWidget(name_lbl)
        info_box.addWidget(id_lbl)
        lay.addLayout(info_box, 1)

        cat_lbl = t.label(category_badge_html(category), "badge")
        cat_lbl.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(cat_lbl)

    def _on_check_changed(self, state: int):
        is_checked = (state == Qt.CheckState.Checked.value or state == 2)
        self._update_appearance(is_checked)
        self.toggled.emit(is_checked)

    def _update_appearance(self, is_checked: bool):
        t.set_prop(self, "selected", is_checked)

    def isChecked(self) -> bool:
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool):
        self.checkbox.setChecked(checked)
        self._update_appearance(checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)


def _clock_text(rem_secs: int) -> str:
    hrs, mins, secs = rem_secs // 3600, (rem_secs % 3600) // 60, rem_secs % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"


def _elapsed_permille(session: Dict[str, Any]) -> int:
    total = max(1, session.get("duration_minutes", 60) * 60)
    return max(0, min(1000, int(1000 * (1 - session.get("remaining_seconds", 0) / total))))


class FocusModeDialog(QDialog):
    """Configure, launch and monitor Focus Sessions."""
    session_changed = pyqtSignal()

    def __init__(self, current_active_app: str = "", current_active_id: str = "", parent=None):
        super().__init__(parent)
        self.current_active_app = current_active_app
        self.current_active_id = current_active_id
        self.app_items: List[FocusAppItem] = []
        self.body: Optional[QWidget] = None

        self.setWindowTitle("QHealth — Focus session")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)

        self._build_ui()

        # Timer to update remaining countdown when active
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_status)
        self.timer.start(1000)

    def _build_ui(self):
        # Rebuild into a fresh container so nothing from the previous state lingers
        if self.body is not None:
            self.body.deleteLater()
        self.__dict__.pop("clock_lbl", None)
        self.body = QWidget(self)
        self.main_lay = QVBoxLayout(self.body)
        self.main_lay.setContentsMargins(26, 24, 26, 22)
        self.main_lay.setSpacing(14)
        self._outer.addWidget(self.body)

        session = get_focus_session()
        if session.get("active"):
            self._build_active_session_ui(session)
        else:
            self._build_start_session_ui()
        self.setFixedSize(580, 520 if session.get("active") else 690)
        for btn in self.body.findChildren(QPushButton):
            btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def _build_active_session_ui(self, session: Dict[str, Any]):
        hdr_row = QHBoxLayout()
        badge = t.label("● Focus session active", "badge")
        t.set_prop(badge, "tone", "accent")
        hdr_row.addWidget(badge)
        hdr_row.addStretch()
        self.main_lay.addLayout(hdr_row)

        # Countdown
        hud_card = QFrame()
        hud_card.setProperty("class", "Card")
        h_lay = QVBoxLayout(hud_card)
        h_lay.setContentsMargins(28, 26, 28, 24)
        h_lay.setSpacing(6)

        self.clock_lbl = t.label(_clock_text(session.get("remaining_seconds", 0)), "clock")
        self.clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_lbl.setAccessibleName("Time remaining")
        h_lay.addWidget(self.clock_lbl)

        tot_mins = session.get('duration_minutes', 60)
        sub_clock = t.label(f"remaining of a {tot_mins}-minute session", "caption")
        sub_clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_lay.addWidget(sub_clock)
        h_lay.addSpacing(10)
        self.focus_progress = QProgressBar()
        self.focus_progress.setFixedHeight(6)
        self.focus_progress.setTextVisible(False)
        self.focus_progress.setMaximum(1000)
        self.focus_progress.setValue(_elapsed_permille(session))
        h_lay.addWidget(self.focus_progress)
        self.main_lay.addWidget(hud_card)

        # Allowed apps
        self.main_lay.addWidget(t.label("ALLOWED APPS", "overline"))
        apps_card = QFrame()
        apps_card.setProperty("class", "Card")
        apps_lay = QHBoxLayout(apps_card)
        apps_lay.setContentsMargins(14, 12, 14, 12)
        apps_lay.setSpacing(8)

        allowed_list = session.get("allowed_apps", [])
        if not allowed_list:
            apps_lay.addWidget(t.label("None — total lockdown. Only system apps can run.", "caption"))
        for a_id in allowed_list[:5]:
            res = app_resolver.resolve(a_id)
            d_name = res.get("display_name", a_id.title())
            chip = QFrame()
            chip.setProperty("class", "Tile")
            c_lay = QHBoxLayout(chip)
            c_lay.setContentsMargins(8, 5, 10, 5)
            c_lay.setSpacing(6)
            ico = t.label()
            ico.setFixedSize(18, 18)
            ico.setPixmap(get_app_icon_pixmap(res.get("icon", a_id), d_name, 18))
            c_lay.addWidget(ico)
            c_lay.addWidget(t.label(d_name if len(d_name) <= 16 else d_name[:14] + "…", "h3"))
            apps_lay.addWidget(chip)
        if len(allowed_list) > 5:
            more = t.label(f"+{len(allowed_list) - 5} more", "caption")
            more.setToolTip(", ".join(allowed_list[5:]))
            apps_lay.addWidget(more)
        apps_lay.addStretch()
        self.main_lay.addWidget(apps_card)

        warn = t.label("Strict mode: anything not on this list is closed as soon as it opens.", "banner")
        t.set_prop(warn, "tone", "warn")
        warn.setWordWrap(True)
        self.main_lay.addWidget(warn)

        self.main_lay.addStretch()

        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        btn_extend = QPushButton("+15 min")
        btn_extend.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_extend.clicked.connect(self._extend_focus_time)
        btn_box.addWidget(btn_extend)

        btn_stop = QPushButton("End early")
        btn_stop.setProperty("class", "Danger")
        btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_stop.clicked.connect(self._end_session_early)
        btn_box.addWidget(btn_stop)
        btn_box.addStretch()

        btn_close = QPushButton("Keep focusing")
        btn_close.setProperty("class", "Primary")
        btn_close.setMinimumWidth(170)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setDefault(True)
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)

        self.main_lay.addLayout(btn_box)

    def _build_start_session_ui(self):
        # 1. Header
        hdr = QHBoxLayout()
        hdr.setSpacing(14)
        icon_tile = QFrame()
        icon_tile.setProperty("class", "Tile")
        icon_tile.setFixedSize(46, 46)
        it_lay = QVBoxLayout(icon_tile)
        it_lay.setContentsMargins(0, 0, 0, 0)
        ico = t.label()
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico.setPixmap(pixmap("focus", t.ACCENT, 24))
        it_lay.addWidget(ico)
        hdr.addWidget(icon_tile)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(t.label("Start a focus session", "h1"))
        title_box.addWidget(t.label("Only the apps you allow can run until the timer ends.", "caption"))
        hdr.addLayout(title_box, 1)
        self.main_lay.addLayout(hdr)
        self.main_lay.addSpacing(4)

        # 2. Duration
        dur_card = QFrame()
        dur_card.setProperty("class", "Card")
        dur_lay = QVBoxLayout(dur_card)
        dur_lay.setContentsMargins(16, 14, 16, 14)
        dur_lay.setSpacing(10)

        dur_top = QHBoxLayout()
        dur_top.addWidget(t.label("DURATION", "overline"))
        dur_top.addStretch()
        self.dur_val_display = t.label("60 min · 1 focus hour", "mono-strong")
        dur_top.addWidget(self.dur_val_display)
        dur_lay.addLayout(dur_top)

        presets_row = QHBoxLayout()
        presets_row.setSpacing(10)
        presets = QFrame()
        presets.setProperty("class", "Segmented")
        p_lay = QHBoxLayout(presets)
        p_lay.setContentsMargins(3, 3, 3, 3)
        p_lay.setSpacing(2)
        self.dur_radios = {}
        for mins, text in [(25, "25 min"), (45, "45 min"), (60, "1 hour"), (120, "2 hours")]:
            btn = QPushButton(text)
            btn.setProperty("class", "Segment")
            btn.setCheckable(True)
            btn.setChecked(mins == 60)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, m=mins: self._on_preset_clicked(m))
            p_lay.addWidget(btn)
            self.dur_radios[mins] = btn
        presets_row.addWidget(presets)
        presets_row.addStretch()
        presets_row.addWidget(t.label("Custom", "caption"))
        self.spin_custom = QSpinBox()
        self.spin_custom.setRange(5, 720)
        self.spin_custom.setValue(60)
        self.spin_custom.setSuffix(" min")
        self.spin_custom.setMinimumWidth(96)
        self.spin_custom.setAccessibleName("Custom duration in minutes")
        self.spin_custom.valueChanged.connect(self._on_custom_spin_changed)
        presets_row.addWidget(self.spin_custom)
        dur_lay.addLayout(presets_row)
        self.main_lay.addWidget(dur_card)

        # 3. Allowlist
        apps_top = QHBoxLayout()
        apps_top.setSpacing(10)
        apps_top.addWidget(t.label("ALLOWED APPS", "overline"))
        self.selected_counter_lbl = t.label("0 selected", "badge")
        apps_top.addWidget(self.selected_counter_lbl)
        apps_top.addStretch()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search apps")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.addAction(icon("search", t.TEXT_3, size=16), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setMinimumWidth(210)
        self.search_input.setAccessibleName("Search applications")
        self.search_input.textChanged.connect(self._filter_app_items)
        apps_top.addWidget(self.search_input)
        self.main_lay.addLayout(apps_top)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        chips_row.addWidget(t.label("Quick pick:", "caption"))
        if self.current_active_id and not is_immune(self.current_active_id):
            app_disp = self.current_active_app or self.current_active_id
            disp_short = app_disp if len(app_disp) <= 18 else app_disp[:16] + "…"
            btn_active_only = QPushButton(f"Only {disp_short}")
            btn_active_only.setToolTip(f"Allow only {app_disp} during this session")
            btn_active_only.clicked.connect(self._select_current_active_only)
            chips_row.addWidget(btn_active_only)
        for text, slot in (("Development", self._select_dev_only), ("Browsers", self._select_browsers_only)):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            chips_row.addWidget(btn)
        chips_row.addStretch()
        btn_clear = QPushButton("Clear")
        btn_clear.setProperty("class", "Ghost")
        btn_clear.clicked.connect(self._clear_all_apps)
        chips_row.addWidget(btn_clear)
        self.main_lay.addLayout(chips_row)

        list_card = QFrame()
        list_card.setProperty("class", "Card")
        lc_lay = QVBoxLayout(list_card)
        lc_lay.setContentsMargins(6, 6, 4, 6)
        self.scroll_area = QScrollArea()
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_lay = QVBoxLayout(self.scroll_widget)
        self.scroll_lay.setContentsMargins(0, 0, 4, 0)
        self.scroll_lay.setSpacing(4)
        self.scroll_area.setWidget(self.scroll_widget)
        lc_lay.addWidget(self.scroll_area)
        self.main_lay.addWidget(list_card, 1)

        self._populate_app_list()

        # 4. Options + actions
        self.chk_kill_running = QCheckBox("Close running apps that aren't allowed as soon as the session starts")
        self.chk_kill_running.setChecked(True)
        self.chk_kill_running.setCursor(Qt.CursorShape.PointingHandCursor)
        self.main_lay.addWidget(self.chk_kill_running)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setProperty("class", "Ghost")
        btn_cancel.setMinimumWidth(90)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        actions_row.addWidget(btn_cancel)
        actions_row.addStretch()

        self.btn_start = QPushButton("Start 60-minute session")
        self.btn_start.setProperty("class", "Primary")
        self.btn_start.setMinimumWidth(230)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setDefault(True)
        self.btn_start.clicked.connect(self._start_session)
        actions_row.addWidget(self.btn_start)

        self.main_lay.addLayout(actions_row)
        self._update_selected_counter()

    def _on_preset_clicked(self, mins: int):
        for m, btn in self.dur_radios.items():
            btn.setChecked(m == mins)
        self.spin_custom.setValue(mins)
        self._set_duration_labels(mins)

    def _on_custom_spin_changed(self, val: int):
        for m, btn in self.dur_radios.items():
            btn.setChecked(m == val)
        self._set_duration_labels(val)

    def _set_duration_labels(self, mins: int):
        self.btn_start.setText(f"Start {mins}-minute session")
        self.dur_val_display.setText("60 min · 1 focus hour" if mins == 60 else f"{mins} min")

    def _update_selected_counter(self):
        count = sum(1 for item in self.app_items if item.isChecked())
        self.selected_counter_lbl.setText(f"{count} selected")
        t.set_prop(self.selected_counter_lbl, "tone", "accent" if count > 0 else "")

    def _populate_app_list(self):
        self.app_items.clear()

        seen_apps = set()
        apps_to_add = []

        try:
            stats = get_stats_by_range("week")
            for a in stats.get("apps", []):
                a_id = a.get("app_id", "").lower().strip()
                if a_id and not is_immune(a_id) and a_id not in seen_apps:
                    seen_apps.add(a_id)
                    apps_to_add.append({
                        "app_id": a_id,
                        "app_name": a.get("app_name", a_id.title()),
                        "category": a.get("category", "Other"),
                        "icon": a.get("icon", a_id)
                    })
        except Exception:
            pass

        if IS_WINDOWS:
            # No .desktop catalogue on Windows: also offer whatever has a window open right now
            from qhealth_core import win32
            for pid, name in running_gui_apps():
                if not app_resolver.is_known(name):
                    path = win32.process_path(pid)
                    app_resolver.register_app(name, win32.file_description(path) if path else "", path)

        for app_id, info in list(app_resolver._apps_cache.items()):
            a_id = app_id.lower().strip()
            if a_id not in seen_apps and not is_immune(a_id):
                seen_apps.add(a_id)
                apps_to_add.append({
                    "app_id": a_id,
                    "app_name": info.get("display_name", a_id.title()),
                    "category": info.get("category", "Other"),
                    "icon": info.get("icon", a_id)
                })

        apps_to_add.sort(key=lambda x: x["app_name"].lower())

        for a in apps_to_add:
            item = FocusAppItem(a["app_id"], a["app_name"], a["icon"], a["category"], self.scroll_widget)
            item.toggled.connect(lambda _: self._update_selected_counter())
            if self.current_active_id and (a["app_id"] == self.current_active_id.lower().strip()):
                item.setChecked(True)
            self.scroll_lay.addWidget(item)
            self.app_items.append(item)

        self.scroll_lay.addStretch()
        self._update_selected_counter()

    def _filter_app_items(self, text: str):
        query = text.lower().strip()
        for item in self.app_items:
            matches = (query in item.app_name.lower() or
                       query in item.app_id.lower() or
                       query in item.category.lower())
            item.setVisible(matches)

    def _select_current_active_only(self):
        for item in self.app_items:
            matches = (item.app_id == self.current_active_id.lower().strip() or
                       item.app_name.lower() == self.current_active_app.lower().strip())
            item.setChecked(matches)
        self._update_selected_counter()

    def _select_dev_only(self):
        for item in self.app_items:
            item.setChecked(item.category == "Development")
        self._update_selected_counter()

    def _select_browsers_only(self):
        browser_tokens = {"browsing", "browser", "firefox", "brave", "chrome", "chromium", "zen", "opera", "vivaldi", "edge"}
        for item in self.app_items:
            is_browser = (item.category == "Browsing" or any(b in item.app_id for b in browser_tokens))
            item.setChecked(is_browser)
        self._update_selected_counter()

    def _clear_all_apps(self):
        for item in self.app_items:
            item.setChecked(False)
        self._update_selected_counter()

    def _extend_focus_time(self):
        session = get_focus_session()
        if session.get("active"):
            cur_end = float(session.get("end_time", time.time()))
            new_end = cur_end + 900 # +15 mins
            session["end_time"] = new_end
            session["duration_minutes"] = session.get("duration_minutes", 60) + 15
            import json
            from qhealth_core.db import set_setting
            set_setting("focus_session", json.dumps(session))
            self.session_changed.emit()
            self._refresh_status()

    def _start_session(self):
        duration = self.spin_custom.value()
        selected_apps = [item.app_id for item in self.app_items if item.isChecked()]

        if not selected_apps:
            reply = QMessageBox.question(
                self,
                "No Apps Selected",
                "You haven't selected any allowed applications. During this focus session, all non-system apps will be force-closed.\n\nDo you want to proceed with total focus lockdown?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        start_focus_session(duration, selected_apps)

        if self.chk_kill_running.isChecked() and selected_apps:
            terminate_unallowed_apps_on_start(selected_apps)

        self.session_changed.emit()
        self.accept()

    def _end_session_early(self):
        reply = QMessageBox.question(
            self,
            "End Focus Session",
            "Are you sure you want to end this focus session early?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            stop_focus_session()
            self.session_changed.emit()
            self.accept()

    def _refresh_status(self):
        session = get_focus_session()
        if session.get("active"):
            if hasattr(self, "clock_lbl"):
                self.clock_lbl.setText(_clock_text(session.get("remaining_seconds", 0)))
                self.focus_progress.setValue(_elapsed_permille(session))
        else:
            if hasattr(self, "clock_lbl"):
                self._build_ui()

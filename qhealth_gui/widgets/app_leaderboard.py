from typing import List, Dict, Any, Callable, Optional, Tuple
from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QColor, QPainter, QPen, QFontMetrics, QFont
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QWidget, QSizePolicy,
    QListWidget, QListWidgetItem, QStyledItemDelegate, QStyle, QAbstractItemView
)
from .. import theme as t
from ..icons import icon, pixmap
from ..utils import format_duration, format_number, get_app_icon_pixmap, get_app_color

ROW_H, ROW_GAP = 58, 6
NUM_COLS = (("KEYS", 64), ("CLICKS", 64), ("TIME", 74))
TONES = {"good": t.GOOD, "warn": t.WARN, "bad": t.BAD}


def row_columns(left: float, width: float) -> Dict[str, Tuple[float, float]]:
    """Horizontal (x, width) slots shared by the painted rows and the caption header, so they always align."""
    x = left + 12
    cols = {"rank": (x, 26.0)}
    x += 26 + 12
    cols["icon"] = (x, 36.0)
    x += 36 + 12
    right = left + width - 14
    cols["chevron"] = (right - 16, 16.0)
    right -= 16 + 12
    for name, w in reversed(NUM_COLS):
        cols[name] = (right - w, float(w))
        right -= w + 12
    flex = max(40.0, right - x)
    cols["name"] = (x, flex * 0.6 - 6)
    cols["share"] = (x + flex * 0.6 + 6, flex * 0.4 - 6)
    return cols


def budget_badge(app_data: Dict[str, Any], can_block: bool = True) -> Tuple[str, str]:
    budget_mins = app_data.get("budget_minutes")
    if not budget_mins:
        return "", ""
    b_pct = app_data.get("budget_percentage", 0)
    # Weekly/monthly usage past N x the daily limit, or a past day, is not "blocked now"
    if can_block and b_pct is not None and b_pct >= 100 and app_data.get("block_on_exceed", False):
        return f"Blocked · {b_pct}%", "bad"
    tone = "good" if b_pct is None or b_pct < 80 else ("warn" if b_pct < 100 else "bad")
    return (f"{b_pct}% of {budget_mins}m limit" if b_pct is not None else f"{budget_mins}m limit"), tone


class AppRowDelegate(QStyledItemDelegate):
    """Paints a whole leaderboard row. No child widgets per row: the list stays instant at any length."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.f_name = t.font(13, QFont.Weight.DemiBold)
        self.f_caption = t.font(12)
        self.f_badge = t.font(11, QFont.Weight.DemiBold)
        self.f_mono = t.font(12, mono=True)
        self.f_mono_strong = t.font(13, QFont.Weight.DemiBold, mono=True)
        self.chevron = pixmap("chevron-right", t.TEXT_3, 16)

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_H)

    def paint(self, p: QPainter, option, index):
        app, rank, color, can_block = index.data(Qt.ItemDataRole.UserRole)
        r = QRectF(option.rect).adjusted(0, 0, 0, -ROW_GAP)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
        cols = row_columns(r.left(), r.width())
        top, cy = r.top(), r.center().y()

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(t.ACCENT if focused else (t.BORDER_STRONG if hovered else t.RAISED)), 1))
        p.setBrush(QColor(t.HOVER if hovered else t.RAISED))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        def text(slot, y, h, s, font, color_hex, align=Qt.AlignmentFlag.AlignLeft):
            x, w = cols[slot] if isinstance(slot, str) else slot
            p.setFont(font)
            p.setPen(QColor(color_hex))
            s = QFontMetrics(font).elidedText(s, Qt.TextElideMode.ElideRight, int(w))
            p.drawText(QRectF(x, y, w, h), align | Qt.AlignmentFlag.AlignVCenter, s)

        right = Qt.AlignmentFlag.AlignRight
        text("rank", top, r.height(), str(rank + 1), self.f_mono, t.TEXT_3, right)

        ix, _ = cols["icon"]
        p.setPen(QPen(QColor(t.BORDER), 1))
        p.setBrush(QColor(t.SURFACE))
        p.drawRoundedRect(QRectF(ix + 0.5, cy - 17.5, 35, 35), 9, 9)
        name = app.get("app_name", "Unknown")
        app_id = app.get("app_id", "")
        p.drawPixmap(int(ix + 5), int(cy - 13), get_app_icon_pixmap(app.get("icon", app_id), name, 26))

        nx, nw = cols["name"]
        text("name", top + 8, 20, name, self.f_name, t.TEXT)
        id_text = app_id or "application"
        badge, tone = budget_badge(app, can_block)
        id_w = min(QFontMetrics(self.f_caption).horizontalAdvance(id_text) + 2, nw * (0.55 if badge else 1.0))
        text((nx, id_w), top + 28, 16, id_text, self.f_caption, t.TEXT_3)
        if badge:
            bw = QFontMetrics(self.f_badge).horizontalAdvance(badge) + 14
            pill = QRectF(nx + id_w + 8, top + 29, min(bw, nx + nw - (nx + id_w + 8)), 16)
            if pill.width() > 24:
                c = QColor(TONES[tone])
                fill, edge = QColor(c), QColor(c)
                fill.setAlphaF(0.10)
                edge.setAlphaF(0.28)
                p.setPen(QPen(edge, 1))
                p.setBrush(fill)
                p.drawRoundedRect(pill, 8, 8)
                text((pill.x() + 7, pill.width() - 14), pill.y(), 16, badge, self.f_badge, TONES[tone])

        sx, sw = cols["share"]
        pct = app.get("percentage", 0.0)
        text("share", top + 8, 16, f"{pct}% of time", self.f_caption, t.TEXT_3, right)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.BORDER_STRONG))
        p.drawRoundedRect(QRectF(sx, top + 32, sw, 4), 2, 2)
        if pct > 0:
            p.setBrush(color)
            p.drawRoundedRect(QRectF(sx, top + 32, max(4.0, sw * min(100.0, pct) / 100.0), 4), 2, 2)

        text("KEYS", top, r.height(), format_number(app.get("keystrokes", 0)), self.f_mono, t.TEXT_2, right)
        text("CLICKS", top, r.height(), format_number(app.get("clicks", 0)), self.f_mono, t.TEXT_2, right)
        text("TIME", top, r.height(), format_duration(app.get("duration", 0)), self.f_mono_strong, t.TEXT, right)
        p.drawPixmap(int(cols["chevron"][0]), int(cy - 8), self.chevron)
        p.restore()


class _AppList(QListWidget):
    """Enter / Space open the current row, like a click."""

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.currentItem():
            self.itemClicked.emit(self.currentItem())
            return
        super().keyPressEvent(event)


class _ColumnHeader(QWidget):
    def __init__(self, view: QListWidget, parent=None):
        super().__init__(parent)
        self.view = view
        self.setFixedHeight(18)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setFont(t.font(11, QFont.Weight.DemiBold))
        p.setPen(QColor(t.TEXT_3))
        cols = row_columns(0, self.view.viewport().width())
        x, w = cols["name"]
        p.drawText(QRectF(x, 0, w, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "APP")
        for name, _ in NUM_COLS:
            x, w = cols[name]
            p.drawText(QRectF(x, 0, w, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, name)
        p.end()


class AppLeaderboardWidget(QFrame):
    SORTS = (("duration", "Time"), ("keystrokes", "Keys"), ("clicks", "Clicks"))

    def __init__(self, on_app_click: Optional[Callable[[Dict[str, Any]], None]] = None, parent=None):
        super().__init__(parent)
        self.on_app_click = on_app_click
        self.setProperty("class", "Card")

        self.apps: List[Dict[str, Any]] = []
        self.sort_by = "duration"
        self.search_text = ""
        self.can_block = True

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(t.PAD, t.PAD, t.PAD - 6, t.PAD)
        main_lay.setSpacing(12)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(t.label("Leaderboard", "h2"))
        self.count_lbl = t.label("0 applications tracked", "caption")
        title_box.addWidget(self.count_lbl)
        top_bar.addLayout(title_box)
        top_bar.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search apps")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.addAction(icon("search", t.TEXT_3, size=16), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setMinimumWidth(200)
        self.search_input.setMaximumWidth(280)
        self.search_input.setAccessibleName("Search applications")
        self.search_input.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_input)

        sort_frame = QFrame()
        sort_frame.setProperty("class", "Segmented")
        s_lay = QHBoxLayout(sort_frame)
        s_lay.setContentsMargins(3, 3, 3, 3)
        s_lay.setSpacing(2)
        sort_btns = []
        for mode, text in self.SORTS:
            btn = QPushButton(text)
            btn.setProperty("class", "Segment")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"Sort by {text.lower()}")
            btn.clicked.connect(lambda _, m=mode: self._set_sort(m))
            s_lay.addWidget(btn)
            sort_btns.append(btn)
        self.btn_time, self.btn_keys, self.btn_clicks = sort_btns
        self.btn_time.setChecked(True)
        top_bar.addWidget(sort_frame)
        top_bar.addSpacing(6)
        main_lay.addLayout(top_bar)

        self.list = _AppList()
        self.list.setItemDelegate(AppRowDelegate(self.list))
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.list.setMouseTracking(True)
        self.list.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.list.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.list.setAccessibleName("Applications ranked by the selected metric. Enter opens details")
        self.list.itemClicked.connect(lambda item: self.on_app_click and self.on_app_click(item.data(Qt.ItemDataRole.UserRole)[0]))

        self.header = _ColumnHeader(self.list)
        self.list.verticalScrollBar().rangeChanged.connect(lambda *_: self.header.update())
        main_lay.addWidget(self.header)
        main_lay.addWidget(self.list, 1)

        self.empty_lbl = t.label("", "empty")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.empty_lbl.setWordWrap(True)
        self.empty_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        main_lay.addWidget(self.empty_lbl, 1)
        self._refresh_list()  # update_apps([]) is a no-op, so render the empty state now

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.header.update()

    def _set_sort(self, mode: str):
        self.sort_by = mode
        self.btn_time.setChecked(mode == "duration")
        self.btn_keys.setChecked(mode == "keystrokes")
        self.btn_clicks.setChecked(mode == "clicks")
        self._refresh_list()

    def _on_search_changed(self, text: str):
        self.search_text = text.lower().strip()
        self._refresh_list()

    def update_apps(self, apps: List[Dict[str, Any]], can_block: bool = True):
        if self.apps == apps and self.can_block == can_block:
            return
        self.apps = apps
        self.can_block = can_block
        self.count_lbl.setText(f"{len(apps)} application{'s' if len(apps) != 1 else ''} tracked")
        self._refresh_list()

    def _refresh_list(self):
        # Colour follows the app (its screen-time rank, as on Overview), never the current sort position
        color_rank = {a.get("app_id", ""): i for i, a in enumerate(self.apps)}
        filtered = [
            a for a in self.apps
            if not self.search_text or self.search_text in a.get("app_name", "").lower() or self.search_text in a.get("app_id", "").lower()
        ]
        filtered.sort(key=lambda x: x.get(self.sort_by, 0), reverse=True)

        if not self.apps:
            self.empty_lbl.setText("No application activity in this range yet.\nApps appear here as soon as you use them.")
        elif not filtered:
            self.empty_lbl.setText(f"No apps match “{self.search_text}”.")
        self.empty_lbl.setVisible(not filtered)
        self.list.setVisible(bool(filtered))
        self.header.setVisible(bool(filtered))

        rows = [(app, idx, get_app_color(app.get("app_name", ""), color_rank.get(app.get("app_id", ""), idx)), self.can_block)
                for idx, app in enumerate(filtered)]
        if self.list.count() != len(rows):
            self.list.clear()
            for _ in rows:
                self.list.addItem(QListWidgetItem())
        # Only rows whose data changed get repainted; scroll position and keyboard focus are kept
        for i, row in enumerate(rows):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) != row:
                app = row[0]
                dur = format_duration(app.get("duration", 0))
                item.setData(Qt.ItemDataRole.UserRole, row)
                item.setData(Qt.ItemDataRole.AccessibleTextRole, f"{app.get('app_name', '')}, {dur}, {app.get('percentage', 0)}% of screen time")
                item.setToolTip(f"{app.get('app_name', '')}\n{dur}  ·  {app.get('keystrokes', 0):,} keys  ·  {app.get('clicks', 0):,} clicks")

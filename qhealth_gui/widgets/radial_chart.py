import math
from typing import List, Dict, Any, Callable, Optional
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QToolTip, QSizePolicy, QBoxLayout
from PyQt6.QtGui import QPainter, QPen, QColor, QFont
from .. import theme as t
from ..utils import format_duration, format_number, get_app_color, get_app_icon_pixmap
from .common import ClickableFrame, card_header, sync_rows

TOP_N = 5


class RadialRingPainter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.total_seconds = 0
        self.apps: List[Dict[str, Any]] = []
        self.hover = -1
        self.arc_spans = []  # (start_deg_from_top, span_deg, idx)
        self._geom = (0.0, 0.0, 0.0, 0.0)  # cx, cy, radius, stroke
        self.setMouseTracking(True)
        self.setAccessibleName("Screen time share by application")

    def set_data(self, total_seconds: int, apps: List[Dict[str, Any]]):
        self.total_seconds = total_seconds
        self.apps = apps
        self.setAccessibleDescription(
            ", ".join(f"{a.get('app_name', '')} {a.get('percentage', 0)}%" for a in apps[:TOP_N]) or "No activity"
        )
        self.update()

    def _hit(self, pos) -> int:
        cx, cy, r, stroke = self._geom
        dx, dy = pos.x() - cx, pos.y() - cy
        dist = math.hypot(dx, dy)
        if dist < r - stroke / 2:
            return -2  # centre
        if dist > r + stroke / 2 + 6:
            return -1
        angle = (math.degrees(math.atan2(dy, dx)) + 90) % 360
        return next((idx for start, span, idx in self.arc_spans if start <= angle <= start + span), -1)

    def mouseMoveEvent(self, event):
        idx = self._hit(event.position())
        if idx != self.hover:
            self.hover = idx
            self.update()
        gp = event.globalPosition().toPoint()
        if idx >= 0:
            app = self.apps[idx]
            QToolTip.showText(gp, (
                f"{app.get('app_name', 'Unknown')}\n"
                f"{format_duration(app.get('duration', 0))}  ·  {app.get('percentage', 0.0)}% of screen time\n"
                f"{format_number(app.get('keystrokes', 0))} keys  ·  {format_number(app.get('clicks', 0))} clicks"
            ), self)
        elif idx == -2:
            QToolTip.showText(gp, f"Total screen time: {format_duration(self.total_seconds)}", self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, event):
        self.hover = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        size = max(120.0, min(240.0, min(w, h) - 16))
        stroke = max(12.0, min(20.0, size * 0.085))
        r = (size - stroke) / 2
        cx, cy = w / 2, h / 2
        self._geom = (cx, cy, r, stroke)
        ring = QRectF(cx - r, cy - r, 2 * r, 2 * r)

        track = QPen(QColor(t.RAISED), stroke)
        track.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(track)
        p.drawEllipse(ring)

        self.arc_spans = []
        if self.total_seconds > 0:
            gap = math.degrees(2.5 / max(1.0, r))  # 2.5px surface gap between segments
            cur = 0.0
            for idx, app in enumerate(self.apps[:TOP_N]):
                dur = app.get("duration", 0)
                if dur <= 0:
                    continue
                span = min(360.0, dur / float(self.total_seconds) * 360.0)
                self.arc_spans.append((cur, span, idx))
                draw_span = span - gap if span > gap * 2 else span
                pen = QPen(get_app_color(app.get("app_name", ""), idx), stroke + (4 if idx == self.hover else 0))
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                p.setPen(pen)
                # Qt angles: 1/16 deg, counter-clockwise from 3 o'clock; clamp to a full turn.
                start16 = int((90 - cur - gap / 2) * 16)
                p.drawArc(ring, start16, -min(360 * 16, int(draw_span * 16)))
                cur += span

        p.setPen(QColor(t.TEXT))
        p.setFont(t.font(max(16, int(size * 0.13)), QFont.Weight.DemiBold))
        p.drawText(QRectF(cx - r, cy - size * 0.13, 2 * r, size * 0.17), Qt.AlignmentFlag.AlignCenter, format_duration(self.total_seconds))
        p.setPen(QColor(t.TEXT_3))
        p.setFont(t.font(12))
        p.drawText(QRectF(cx - r, cy + size * 0.05, 2 * r, 18), Qt.AlignmentFlag.AlignCenter, "screen time")
        p.end()


class LegendRow(ClickableFrame):
    def __init__(self, on_click: Optional[Callable[[Dict[str, Any]], None]], parent=None):
        super().__init__(parent)
        self.app: Dict[str, Any] = {}
        if on_click:
            self.clicked.connect(lambda: on_click(self.app))
        else:
            self.setProperty("class", "Static")
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 12, 7)
        lay.setSpacing(10)
        self.swatch = QFrame()
        self.swatch.setFixedSize(4, 22)
        lay.addWidget(self.swatch)
        self.icon_lbl = t.label()
        self.icon_lbl.setFixedSize(20, 20)
        lay.addWidget(self.icon_lbl)
        self.name_lbl = t.label("", "h3")
        lay.addWidget(self.name_lbl, 1)
        self.dur_lbl = t.label("", "mono-strong")
        lay.addWidget(self.dur_lbl)
        self.pct_lbl = t.label("", "caption")
        self.pct_lbl.setFixedWidth(46)
        self.pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.pct_lbl)

    def set_data(self, app: Dict[str, Any], color: QColor):
        self.app = app
        name = app.get("app_name", "Unknown")
        self.swatch.setStyleSheet(f"background: {color.name()}; border-radius: 2px; border: none;")
        self.icon_lbl.setPixmap(get_app_icon_pixmap(app.get("icon", app.get("app_id", "")), name, 20))
        self.name_lbl.setText(name if len(name) <= 22 else name[:20] + "…")
        self.name_lbl.setToolTip(name)
        self.dur_lbl.setText(format_duration(app.get("duration", 0)))
        self.pct_lbl.setText(f"{app.get('percentage', 0)}%")
        self.setAccessibleName(f"{name}, {format_duration(app.get('duration', 0))}")


class RadialChartWidget(QFrame):
    def __init__(self, parent=None, on_app_click: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__(parent)
        self.setProperty("class", "Card")
        self.setObjectName("RadialCard")
        self.on_app_click = on_app_click

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.PAD, t.PAD, t.PAD, t.PAD)
        layout.setSpacing(12)
        hdr, _, self.tag_lbl = card_header("Top applications", "Share of screen time")
        layout.addLayout(hdr)

        self.content = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.content.setSpacing(t.GAP)
        self.ring_painter = RadialRingPainter(self)
        self.content.addWidget(self.ring_painter, 1)

        legend = QVBoxLayout()
        legend.addStretch()
        self.empty_lbl = t.label("No app activity in this range yet.", "empty")
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        legend.addWidget(self.empty_lbl)
        self.legend_layout = QVBoxLayout()
        self.legend_layout.setSpacing(6)
        self.legend_rows: List[LegendRow] = []
        legend.addLayout(self.legend_layout)
        legend.addStretch()
        self.content.addLayout(legend, 1)
        layout.addLayout(self.content, 1)

    def update_data(self, total_seconds: int, apps: List[Dict[str, Any]], range_type: str = "day"):
        self.ring_painter.set_data(total_seconds, apps)
        top = apps[:TOP_N]
        self.empty_lbl.setVisible(not top)
        items = [(app, get_app_color(app.get("app_name", ""), idx)) for idx, app in enumerate(top)]
        sync_rows(self.legend_rows, self.legend_layout, items, lambda: LegendRow(self.on_app_click, self))

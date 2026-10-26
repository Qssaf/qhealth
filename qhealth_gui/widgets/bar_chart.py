import math
from typing import Any, Callable, Dict, List
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import QSizePolicy, QToolTip, QWidget
from .. import theme as t
from ..utils import format_duration, format_number

HOUR_STEPS = (1, 2, 3, 4, 6, 12)
# Axis maxima with clean halves: durations in seconds, counts as 1/2/4/5 x 10^k
NICE_DURATIONS = [m * 60 for m in (10, 20, 30, 60, 120, 240, 360, 480, 600, 720, 960, 1200, 1440)]


def nice_ceil(value: float, is_duration: bool) -> float:
    if is_duration:
        for step in NICE_DURATIONS:
            if value <= step:
                return step
        return math.ceil(value / 172800) * 172800  # whole 2-day steps
    magnitude = 10 ** math.floor(math.log10(max(value, 1)))
    return next(m * magnitude for m in (1, 2, 4, 5, 10) if value <= m * magnitude)


def axis_duration(seconds: int) -> str:
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0 and seconds < 3600:
        return f"{seconds // 60}m"
    return format_duration(seconds)


def bucket_label(item: Dict[str, Any], range_type: str, index: int) -> str:
    if range_type == "day":
        h = item.get("hour_int", index)
        return f"{h:02d}:00 – {(h + 1) % 24:02d}:00"
    if range_type in ("week", "month"):
        return f"{item.get('label', '')} · {item.get('date', '')}".strip(" ·")
    return item.get("month_str", "")


def bucket_tooltip(item: Dict[str, Any], range_type: str, index: int) -> str:
    return (
        f"{bucket_label(item, range_type, index)}\n"
        f"Active {format_duration(item.get('duration', 0))}  ·  "
        f"{format_number(item.get('keystrokes', 0))} keys  ·  {format_number(item.get('clicks', 0))} clicks"
    )


def duration_value(item: Dict[str, Any]) -> float:
    return item.get("duration", 0)


def input_value(item: Dict[str, Any]) -> float:
    return item.get("keystrokes", 0) + item.get("clicks", 0)


class BarChart(QWidget):
    """Single-series bars over time buckets (hours, days or months), with a recessive grid and hover tooltip."""

    def __init__(self, value: Callable[[Dict[str, Any]], float] = duration_value, color: str = t.SERIES_TIME,
                 axis_format: Callable[[int], str] = axis_duration, day_floor: float = 3600.0, parent=None):
        super().__init__(parent)
        self.value = value
        self.color = color
        self.axis_format = axis_format
        self.day_floor = day_floor   # day view keeps a fixed 1-hour scale so hours compare across days
        self.items: List[Dict[str, Any]] = []
        self.range_type = "day"
        self.hover = -1
        self._cols: List[QRectF] = []
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_data(self, items: List[Dict[str, Any]], range_type: str = "day"):
        self.items = items or []
        self.range_type = range_type
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        idx = next((i for i, r in enumerate(self._cols) if r.contains(pos)), -1)
        if idx != self.hover:
            self.hover = idx
            self.update()
        if idx >= 0:
            QToolTip.showText(event.globalPosition().toPoint(), bucket_tooltip(self.items[idx], self.range_type, idx), self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, event):
        self.hover = -1
        self.update()
        super().leaveEvent(event)

    def _x_label(self, i: int, item: Dict[str, Any]) -> str:
        if self.range_type == "day":
            return f"{item.get('hour_int', i):02d}:00"
        if self.range_type == "week":
            return item.get("label", "")
        if self.range_type == "month":
            return item.get("date", "")[-2:]
        return item.get("label", item.get("month_str", "")[-2:])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._cols = []

        gutter, top, bottom = 48.0, 8.0, 22.0
        w, h = float(self.width()), float(self.height())
        plot_w, plot_h = max(10.0, w - gutter), max(20.0, h - top - bottom)
        base_y = top + plot_h

        values = [self.value(d) for d in self.items]
        peak = max(values + [0])
        is_duration = self.value is duration_value
        scale = nice_ceil(max(peak, 1.0), is_duration)
        if self.range_type == "day" and is_duration:
            scale = max(scale, self.day_floor)

        # Recessive grid: baseline, half, max
        p.setFont(t.font(11))
        for frac in (0.0, 0.5, 1.0):
            y = base_y - frac * plot_h
            p.setPen(QColor(t.BORDER_STRONG if frac == 0 else t.BORDER))
            p.drawLine(int(gutter), int(y), int(w), int(y))
            if frac > 0:
                p.setPen(QColor(t.TEXT_3))
                p.drawText(QRectF(0, y - 8, gutter - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           self.axis_format(int(scale * frac)))

        if not self.items or peak <= 0:
            p.setPen(QColor(t.TEXT_3))
            p.setFont(t.font(12))
            p.drawText(QRectF(gutter, top, plot_w, plot_h), Qt.AlignmentFlag.AlignCenter, "No activity recorded in this range")
            p.end()
            return

        count = len(self.items)
        col_w = plot_w / count
        bar_w = max(2.0, min(28.0, col_w * 0.62))
        bar_color = QColor(self.color)
        hover_color = t.mix(self.color, "#ffffff", 0.22)

        for i, val in enumerate(values):
            col = QRectF(gutter + i * col_w, top, col_w, plot_h)
            self._cols.append(col)
            if i == self.hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 10))
                p.drawRoundedRect(col.adjusted(1, 0, -1, 0), 4, 4)
            if val <= 0:
                continue
            bar_h = max(2.0, (val / scale) * plot_h)
            x = col.center().x() - bar_w / 2
            r = min(4.0, bar_w / 2, bar_h)
            # Rounded data-end, square at the baseline
            path = QPainterPath()
            path.moveTo(x, base_y)
            path.lineTo(x, base_y - bar_h + r)
            path.quadTo(x, base_y - bar_h, x + r, base_y - bar_h)
            path.lineTo(x + bar_w - r, base_y - bar_h)
            path.quadTo(x + bar_w, base_y - bar_h, x + bar_w, base_y - bar_h + r)
            path.lineTo(x + bar_w, base_y)
            path.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(hover_color if i == self.hover else bar_color)
            p.drawPath(path)

        # X labels, thinned to whatever fits
        need = math.ceil(40.0 / col_w)
        step = next((s for s in HOUR_STEPS if s >= need), 12) if self.range_type == "day" else max(1, need)
        p.setFont(t.font(11))
        for i, item in enumerate(self.items):
            if i % step:
                continue
            p.setPen(QColor(t.TEXT if i == self.hover else t.TEXT_3))
            cx = gutter + (i + 0.5) * col_w
            p.drawText(QRectF(cx - 30, base_y + 4, 60, 16), Qt.AlignmentFlag.AlignCenter, self._x_label(i, item))
        p.end()

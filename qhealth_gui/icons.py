"""Painted line icons on a 24-unit grid, so the UI never depends on an icon font or emoji coverage."""
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from . import theme as t


def _polyline(p: QPainter, *pts):
    path = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        path.lineTo(QPointF(*pt))
    p.drawPath(path)


def _draw(p: QPainter, name: str):
    if name == "overview":
        for x, y in ((4, 4), (13, 4), (4, 13), (13, 13)):
            p.drawRoundedRect(QRectF(x, y, 7, 7), 2, 2)
    elif name == "input":
        p.drawRoundedRect(QRectF(2.5, 6, 19, 12), 2.5, 2.5)
        for x in (6.5, 10, 13.5, 17):
            p.drawPoint(QPointF(x, 10))
        p.drawLine(QPointF(8, 14.2), QPointF(16, 14.2))
    elif name == "apps":
        for y, length in ((6, 16), (12, 12), (18, 7)):
            p.drawLine(QPointF(4, y), QPointF(4 + length, y))
    elif name == "focus":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        p.drawEllipse(QPointF(12, 12), 4.2, 4.2)
        p.drawPoint(QPointF(12, 12))
    elif name == "pause":
        p.drawLine(QPointF(9, 6.5), QPointF(9, 17.5))
        p.drawLine(QPointF(15, 6.5), QPointF(15, 17.5))
    elif name == "play":
        path = QPainterPath(QPointF(8.5, 6))
        path.lineTo(18, 12)
        path.lineTo(8.5, 18)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "chevron-left":
        _polyline(p, (14.5, 6), (8.5, 12), (14.5, 18))
    elif name == "chevron-right":
        _polyline(p, (9.5, 6), (15.5, 12), (9.5, 18))
    elif name == "back":
        p.drawLine(QPointF(19, 12), QPointF(5, 12))
        _polyline(p, (11, 6), (5, 12), (11, 18))
    elif name == "calendar":
        p.drawRoundedRect(QRectF(4, 5.5, 16, 14.5), 2.5, 2.5)
        p.drawLine(QPointF(4, 10), QPointF(20, 10))
        p.drawLine(QPointF(8.5, 3.5), QPointF(8.5, 7))
        p.drawLine(QPointF(15.5, 3.5), QPointF(15.5, 7))
    elif name == "search":
        p.drawEllipse(QPointF(10.5, 10.5), 6, 6)
        p.drawLine(QPointF(15, 15), QPointF(20, 20))


def pixmap(name: str, color: str, size: int = 18) -> QPixmap:
    dpr = 2.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    pen = QPen(QColor(color), 1.9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _draw(p, name)
    p.end()
    return pm


def icon(name: str, color: str = t.TEXT_2, on_color: str = "", size: int = 18) -> QIcon:
    """`on_color` tints the checked state (nav items, toggles)."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    if on_color:
        ic.addPixmap(pixmap(name, on_color, size), QIcon.Mode.Normal, QIcon.State.On)
    ic.addPixmap(pixmap(name, t.TEXT_4, size), QIcon.Mode.Disabled, QIcon.State.Off)
    return ic


def toggle_icon(off_name: str, on_name: str, color: str = t.TEXT_2, size: int = 18) -> QIcon:
    """Different glyph per checked state, e.g. pause <-> play."""
    ic = QIcon()
    ic.addPixmap(pixmap(off_name, color, size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(on_name, color, size), QIcon.Mode.Normal, QIcon.State.On)
    return ic

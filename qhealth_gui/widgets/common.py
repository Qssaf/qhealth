from typing import Callable, List, Sequence, Tuple
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget
from .. import theme as t


class ClickableFrame(QFrame):
    """A row that behaves like a button: hover, Tab focus, Enter/Space and click all emit `clicked`."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "Row")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class ShareBar(QWidget):
    """Thin painted share bar. Far cheaper than a per-row styled QProgressBar in long, frequently refreshed lists."""

    def __init__(self, color: str = t.ACCENT, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.color = QColor(color)
        self.setFixedHeight(4)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, percent: float, color: QColor = None):
        percent = max(0.0, min(100.0, float(percent)))
        if percent == self.value and (color is None or color == self.color):
            return
        self.value = percent
        if color is not None:
            self.color = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        r = self.height() / 2
        p.setBrush(QColor(t.HOVER))
        p.drawRoundedRect(QRectF(self.rect()), r, r)
        if self.value > 0:
            p.setBrush(self.color)
            p.drawRoundedRect(QRectF(0, 0, max(self.height(), self.width() * self.value / 100.0), self.height()), r, r)
        p.end()


class RampLegend(QWidget):
    """'Less ▢▢▢▢▢ More' key for a single-hue sequential ramp."""

    def __init__(self, base: str, parent=None):
        super().__init__(parent)
        self.base = base
        self.setFixedSize(132, 16)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(t.font(11))
        p.setPen(QColor(t.TEXT_3))
        p.drawText(QRectF(0, 0, 30, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "Less")
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(5):
            p.setBrush(t.heat(self.base, i / 4.0))
            p.drawRoundedRect(QRectF(36 + i * 13, 3, 10, 10), 2.5, 2.5)
        p.setPen(QColor(t.TEXT_3))
        p.drawText(QRectF(102, 0, 30, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "More")
        p.end()


def card_header(title: str, aside: str = "") -> Tuple[QHBoxLayout, QLabel, QLabel]:
    """Card title on the left, muted context on the right."""
    row = QHBoxLayout()
    row.setSpacing(t.GAP_SM)
    title_lbl = t.label(title, "h2")
    aside_lbl = t.label(aside, "caption")
    row.addWidget(title_lbl)
    row.addStretch()
    row.addWidget(aside_lbl)
    return row, title_lbl, aside_lbl


def sync_rows(rows: List[QWidget], layout: QBoxLayout, items: Sequence[tuple], make: Callable[[], QWidget]) -> None:
    """Update row widgets in place (keeps hover, focus and scroll position across 3 s refreshes).
    Rows are created on demand at the top of `layout`; each gets `set_data(*item)`."""
    for i, item in enumerate(items):
        if i == len(rows):
            rows.append(make())
            layout.insertWidget(i, rows[i])
        rows[i].set_data(*item)
        if rows[i].isHidden():
            rows[i].show()
    for row in rows[len(items):]:
        if not row.isHidden():
            row.hide()

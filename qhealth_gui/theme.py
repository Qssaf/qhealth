"""QHealth design tokens ("Quiet Instrument", Tide palette) and the small helpers every widget shares.

All colours, type and spacing live here; widgets and the stylesheet reference these names
instead of raw hex so the whole UI can be retuned in one place.
"""
from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
from PyQt6.QtGui import QColor, QFont, QFontDatabase
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QLabel, QWidget

# --- Surfaces: elevation is expressed as a lighter step, never a shadow ---
CANVAS = "#0d0f12"
SIDEBAR = "#111317"
SURFACE = "#16191e"        # cards
RAISED = "#1c2026"         # rows, inputs, tiles inside cards
HOVER = "#232830"
OVERLAY = "#1a1d23"        # menus, popups, tooltips
BORDER = "#242931"
BORDER_STRONG = "#323843"

# --- Ink (contrast vs SURFACE: 15.2 / 7.6 / 5.1 / 2.6) ---
TEXT = "#eceef2"
TEXT_2 = "#a4abb6"
TEXT_3 = "#838b97"
TEXT_4 = "#545b66"         # disabled / decorative only

# --- Brand ---
ACCENT = "#3cc7ad"         # jade (UI: nav, primary buttons, focus rings)
ACCENT_HOVER = "#5ad4bd"
ACCENT_PRESS = "#2fb39b"
ON_ACCENT = "#06201b"

# --- Status (reserved for state; never used as a data series) ---
GOOD = "#4ade80"
WARN = "#fbbf24"
BAD = "#f87171"

# --- Metric identity: the same measure wears the same colour on every screen ---
# Validated as a set (CVD + contrast) on SURFACE. Scrolls are only ever a labelled number, so stay neutral.
SERIES_TIME = "#1fa58c"    # deeper jade: the accent is too light for chart marks
SERIES_KEYS = "#3987e5"
SERIES_CLICKS = "#d95926"
SERIES_SCROLLS = TEXT_3

# Categorical apps palette, fixed order, validated (CVD + contrast) against SURFACE.
CATEGORICAL = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]

# --- Type & spacing ---
FONT_UI = ["Inter", "Segoe UI Variable Text", "Segoe UI", "Noto Sans", "Cantarell", "DejaVu Sans"]
FONT_MONO = ["JetBrains Mono", "JetBrainsMono Nerd Font", "Cascadia Mono", "Consolas", "Hack", "Noto Sans Mono", "DejaVu Sans Mono"]
PAD = 18      # card padding
GAP = 16      # gap between cards
GAP_SM = 8


def first_family(candidates) -> str:
    installed = set(QFontDatabase.families())
    return next((f for f in candidates if f in installed), candidates[-1])


def font(px: int, weight: QFont.Weight = QFont.Weight.Normal, mono: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(FONT_MONO if mono else FONT_UI)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def mix(a: str, b: str, t: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    )


def heat(base: str, t: float) -> QColor:
    """Single-hue sequential ramp: zero recedes into the surface, max is the full hue."""
    if t <= 0:
        return QColor(RAISED)
    return mix(RAISED, base, 0.22 + 0.78 * min(1.0, t))


def ink_on(bg: QColor) -> QColor:
    """Readable text colour for an arbitrary fill."""
    lum = 0.2126 * bg.redF() + 0.7152 * bg.greenF() + 0.0722 * bg.blueF()
    return QColor(CANVAS if lum > 0.45 else TEXT)


def label(text: str = "", role: str = "body", parent: QWidget = None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setProperty("role", role)
    return lbl


def dot(color: str, size: int = 8) -> QFrame:
    d = QFrame()
    d.setFixedSize(size, size)
    d.setStyleSheet(f"background: {color}; border-radius: {size // 2}px; border: none;")
    return d


def set_prop(widget: QWidget, name: str, value) -> None:
    """Set a dynamic property and re-polish so QSS selectors like [tone="bad"] update."""
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.updateGeometry()  # padding/border may have changed the size hint


def fade_in(widget: QWidget, ms: int = 160) -> None:
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

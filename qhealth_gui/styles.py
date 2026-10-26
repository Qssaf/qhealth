from pathlib import Path
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication
from . import theme as t

UI_ASSETS = (Path(__file__).resolve().parent / "assets" / "ui").as_posix()  # shipped as package data


def get_qhealth_stylesheet() -> str:
    mono = t.first_family(t.FONT_MONO)
    accent_soft = t.rgba(t.ACCENT, 0.14)
    accent_line = t.rgba(t.ACCENT, 0.40)
    return f"""
    * {{ outline: none; }}
    QMainWindow, QDialog {{ background: {t.CANVAS}; }}
    QWidget {{ color: {t.TEXT}; font-size: 13px; }}
    QLabel {{ background: transparent; border: none; }}

    /* ---------- Surfaces ---------- */
    QFrame.Sidebar {{ background: {t.SIDEBAR}; border: none; border-right: 1px solid {t.BORDER}; }}
    QFrame.Card {{ background: {t.SURFACE}; border: 1px solid {t.BORDER}; border-radius: 14px; }}
    QFrame.Tile {{ background: {t.RAISED}; border: 1px solid {t.BORDER}; border-radius: 10px; }}
    QFrame.Segmented {{ background: {t.RAISED}; border: 1px solid {t.BORDER}; border-radius: 9px; }}
    QFrame.Divider {{ background: {t.BORDER}; border: none; max-height: 1px; min-height: 1px; }}
    QFrame.Row {{ background: {t.RAISED}; border: 1px solid transparent; border-radius: 10px; }}
    QFrame.Row:hover {{ background: {t.HOVER}; border-color: {t.BORDER_STRONG}; }}
    QFrame.Row:focus {{ border-color: {t.ACCENT}; }}
    QFrame.Row[selected="true"] {{ background: {accent_soft}; border-color: {accent_line}; }}
    QFrame.Static {{ background: {t.RAISED}; border: 1px solid transparent; border-radius: 10px; }}

    /* ---------- Type roles ---------- */
    QLabel[role="brand"] {{ font-size: 16px; font-weight: 700; }}
    QLabel[role="h1"] {{ font-size: 20px; font-weight: 600; }}
    QLabel[role="h2"] {{ font-size: 15px; font-weight: 600; }}
    QLabel[role="h3"] {{ font-size: 13px; font-weight: 600; }}
    QLabel[role="body"] {{ color: {t.TEXT_2}; }}
    QLabel[role="caption"] {{ font-size: 12px; color: {t.TEXT_3}; }}
    QLabel[role="overline"] {{ font-size: 11px; font-weight: 600; color: {t.TEXT_3}; }}
    QLabel[role="metric"] {{ font-size: 24px; font-weight: 600; }}
    QLabel[role="metric-sm"] {{ font-size: 18px; font-weight: 600; }}
    QLabel[role="live"] {{ font-family: "{mono}"; font-size: 20px; font-weight: 600; }}
    QLabel[role="clock"] {{ font-family: "{mono}"; font-size: 52px; font-weight: 600; }}
    QLabel[role="mono"] {{ font-family: "{mono}"; font-size: 12px; color: {t.TEXT_2}; }}
    QLabel[role="mono-strong"] {{ font-family: "{mono}"; font-size: 13px; font-weight: 600; }}
    QLabel[role="empty"] {{ font-size: 12px; color: {t.TEXT_3}; padding: 20px; }}
    QLabel[role="badge"] {{
        font-size: 11px; font-weight: 600; color: {t.TEXT_2};
        background: {t.RAISED}; border: 1px solid {t.BORDER}; border-radius: 9px; padding: 2px 8px;
    }}
    QLabel[role="badge"][tone="good"] {{ color: {t.GOOD}; background: {t.rgba(t.GOOD, 0.10)}; border-color: {t.rgba(t.GOOD, 0.28)}; }}
    QLabel[role="badge"][tone="warn"] {{ color: {t.WARN}; background: {t.rgba(t.WARN, 0.10)}; border-color: {t.rgba(t.WARN, 0.28)}; }}
    QLabel[role="badge"][tone="bad"] {{ color: {t.BAD}; background: {t.rgba(t.BAD, 0.10)}; border-color: {t.rgba(t.BAD, 0.28)}; }}
    QLabel[role="badge"][tone="accent"] {{ color: {t.ACCENT}; background: {accent_soft}; border-color: {t.rgba(t.ACCENT, 0.30)}; }}
    QLabel[role="banner"] {{
        color: {t.TEXT}; background: {t.rgba(t.BAD, 0.10)}; border: 1px solid {t.rgba(t.BAD, 0.30)};
        border-radius: 10px; padding: 8px 12px;
    }}
    QLabel[role="banner"][tone="warn"] {{ background: {t.rgba(t.WARN, 0.08)}; border-color: {t.rgba(t.WARN, 0.28)}; }}
    QLabel[role="status"] {{ font-size: 12px; color: {t.TEXT_2}; }}
    QLabel[role="status"][tone="good"] {{ color: {t.GOOD}; }}
    QLabel[role="status"][tone="warn"] {{ color: {t.WARN}; }}

    /* ---------- Buttons ---------- */
    QPushButton {{
        background: {t.RAISED}; color: {t.TEXT}; border: 1px solid {t.BORDER};
        border-radius: 8px; padding: 6px 12px; font-weight: 500;
    }}
    QPushButton:hover {{ background: {t.HOVER}; border-color: {t.BORDER_STRONG}; }}
    QPushButton:pressed {{ background: {t.RAISED}; }}
    QPushButton:focus {{ border-color: {t.ACCENT}; }}
    QPushButton:checked {{ background: {accent_soft}; border-color: {accent_line}; }}
    QPushButton:disabled {{ color: {t.TEXT_4}; background: transparent; border-color: {t.BORDER}; }}
    QPushButton[active="true"] {{ background: {accent_soft}; border-color: {accent_line}; color: {t.TEXT}; }}

    QPushButton.Primary {{ background: {t.ACCENT}; color: {t.ON_ACCENT}; border: 1px solid {t.ACCENT}; font-weight: 600; padding: 8px 16px; }}
    QPushButton.Primary:hover {{ background: {t.ACCENT_HOVER}; border-color: {t.ACCENT_HOVER}; }}
    QPushButton.Primary:pressed {{ background: {t.ACCENT_PRESS}; border-color: {t.ACCENT_PRESS}; }}
    QPushButton.Primary:focus {{ border-color: {t.TEXT}; }}

    QPushButton.Ghost {{ background: transparent; border-color: transparent; color: {t.TEXT_2}; }}
    QPushButton.Ghost:hover {{ background: {t.RAISED}; color: {t.TEXT}; }}
    QPushButton.Ghost:focus {{ border-color: {t.ACCENT}; }}

    QPushButton.Danger {{ background: {t.rgba(t.BAD, 0.12)}; color: {t.BAD}; border-color: {t.rgba(t.BAD, 0.35)}; }}
    QPushButton.Danger:hover {{ background: {t.rgba(t.BAD, 0.22)}; color: {t.TEXT}; }}

    QPushButton.Nav {{
        background: transparent; border: 1px solid transparent; border-radius: 8px;
        padding: 8px 10px; text-align: left; color: {t.TEXT_2}; font-weight: 500;
    }}
    QPushButton.Nav:hover {{ background: {t.RAISED}; color: {t.TEXT}; }}
    QPushButton.Nav:checked {{ background: {t.rgba(t.ACCENT, 0.12)}; border-color: {t.rgba(t.ACCENT, 0.22)}; color: {t.TEXT}; }}
    QPushButton.Nav:focus {{ border-color: {t.ACCENT}; }}

    QPushButton.Segment {{
        background: transparent; border: 1px solid transparent; border-radius: 6px;
        padding: 5px 12px; color: {t.TEXT_2}; font-weight: 500;
    }}
    QPushButton.Segment:hover {{ color: {t.TEXT}; background: transparent; }}
    QPushButton.Segment:checked {{ background: {t.HOVER}; border-color: {t.BORDER_STRONG}; color: {t.TEXT}; }}
    QPushButton.Segment:focus {{ border-color: {t.ACCENT}; }}

    QPushButton.Icon {{ padding: 0px; }}

    /* ---------- Inputs ---------- */
    QLineEdit, QComboBox, QSpinBox {{
        background: {t.RAISED}; color: {t.TEXT}; border: 1px solid {t.BORDER};
        border-radius: 8px; padding: 6px 10px;
        selection-background-color: {t.rgba(t.ACCENT, 0.35)}; selection-color: {t.TEXT};
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {t.BORDER_STRONG}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {t.ACCENT}; }}
    QComboBox {{ padding-right: 28px; }}
    QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: none; }}
    QComboBox::down-arrow {{ image: url({UI_ASSETS}/chevron-down.svg); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{
        background: {t.OVERLAY}; color: {t.TEXT}; border: 1px solid {t.BORDER_STRONG};
        border-radius: 8px; padding: 4px; selection-background-color: {t.HOVER}; selection-color: {t.TEXT};
    }}
    QSpinBox {{ padding-right: 22px; font-weight: 600; }}
    QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 20px; border: none; background: transparent; }}
    QSpinBox::up-button {{ subcontrol-position: top right; }}
    QSpinBox::down-button {{ subcontrol-position: bottom right; }}
    QSpinBox::up-arrow {{ image: url({UI_ASSETS}/chevron-up.svg); width: 10px; height: 10px; }}
    QSpinBox::down-arrow {{ image: url({UI_ASSETS}/chevron-down.svg); width: 10px; height: 10px; }}

    QCheckBox {{ spacing: 8px; color: {t.TEXT_2}; }}
    QCheckBox:hover {{ color: {t.TEXT}; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid {t.BORDER_STRONG}; background: {t.RAISED}; }}
    QCheckBox::indicator:hover, QCheckBox::indicator:focus {{ border-color: {t.ACCENT}; }}
    QCheckBox::indicator:checked {{ background: {t.ACCENT}; border-color: {t.ACCENT}; image: url({UI_ASSETS}/check.svg); }}

    QProgressBar {{ background: {t.RAISED}; border: none; border-radius: 3px; }}
    QProgressBar::chunk {{ background: {t.ACCENT}; border-radius: 3px; }}
    QProgressBar[tone="good"]::chunk {{ background: {t.GOOD}; }}
    QProgressBar[tone="warn"]::chunk {{ background: {t.WARN}; }}
    QProgressBar[tone="bad"]::chunk {{ background: {t.BAD}; }}

    /* ---------- Scrolling ---------- */
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t.BORDER_STRONG}; min-height: 28px; border-radius: 3px; }}
    QScrollBar::handle:horizontal {{ background: {t.BORDER_STRONG}; min-width: 28px; border-radius: 3px; }}
    QScrollBar::handle:hover {{ background: {t.TEXT_4}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; border: none; background: transparent; }}
    QScrollBar::add-page, QScrollBar::sub-page, QScrollBar::corner {{ background: transparent; }}

    QListView {{ background: transparent; border: none; }}

    /* ---------- Overlays ---------- */
    QToolTip {{
        background: {t.OVERLAY}; color: {t.TEXT}; border: 1px solid {t.BORDER_STRONG};
        border-radius: 8px; padding: 6px 10px; font-size: 12px;
    }}
    QMenu {{ background: {t.OVERLAY}; border: 1px solid {t.BORDER_STRONG}; border-radius: 10px; padding: 4px; }}
    QMenu::item {{ padding: 6px 14px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {t.HOVER}; }}
    QMenu::item:disabled {{ color: {t.TEXT_3}; }}
    QMenu::separator {{ height: 1px; background: {t.BORDER}; margin: 4px 6px; }}
    QMessageBox QPushButton {{ min-width: 76px; }}
    """


def _palette() -> QPalette:
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.CANVAS,
        QPalette.ColorRole.WindowText: t.TEXT,
        QPalette.ColorRole.Base: t.RAISED,
        QPalette.ColorRole.AlternateBase: t.SURFACE,
        QPalette.ColorRole.Text: t.TEXT,
        QPalette.ColorRole.Button: t.RAISED,
        QPalette.ColorRole.ButtonText: t.TEXT,
        QPalette.ColorRole.Highlight: t.ACCENT,
        QPalette.ColorRole.HighlightedText: t.ON_ACCENT,
        QPalette.ColorRole.ToolTipBase: t.OVERLAY,
        QPalette.ColorRole.ToolTipText: t.TEXT,
        QPalette.ColorRole.PlaceholderText: t.TEXT_3,
        QPalette.ColorRole.Link: t.ACCENT,
    }
    for role, hex_color in roles.items():
        pal.setColor(role, QColor(hex_color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.TEXT_4))
    return pal


def apply_theme(app: QApplication) -> None:
    """Fusion + token palette + QSS: identical rendering under Breeze, Kvantum or anything else."""
    if app.property("qhealth_themed"):
        return
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setFont(t.font(13))
    app.setStyleSheet(get_qhealth_stylesheet())
    app.setProperty("qhealth_themed", True)

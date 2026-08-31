def get_qhealth_stylesheet() -> str:
    return """
    QMainWindow {
        background-color: #07090e;
        color: #f1f5f9;
    }

    QWidget {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 13px;
        color: #e2e8f0;
    }

    QScrollArea {
        border: none;
        background-color: transparent;
    }

    QScrollBar:vertical {
        border: none;
        background: rgba(15, 23, 42, 0.4);
        width: 6px;
        margin: 0px;
        border-radius: 3px;
    }

    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.15);
        min-height: 20px;
        border-radius: 3px;
    }

    QScrollBar::handle:vertical:hover {
        background: rgba(56, 189, 248, 0.4);
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QFrame.GlassCard {
        background-color: rgba(13, 18, 29, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
    }

    QFrame.GlassCardInner {
        background-color: rgba(15, 23, 42, 0.55);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 10px;
    }

    QFrame.GlassCardInner:hover {
        border-color: rgba(56, 189, 248, 0.35);
        background-color: rgba(18, 28, 48, 0.7);
    }

    QPushButton.TabBtn {
        background-color: transparent;
        color: #94a3b8;
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 6px 16px;
        font-weight: 600;
        font-size: 12px;
    }

    QPushButton.TabBtn:hover {
        color: #38bdf8;
        background-color: rgba(56, 189, 248, 0.08);
        border: 1px solid rgba(56, 189, 248, 0.2);
    }

    QPushButton.TabBtn:checked {
        background-color: rgba(14, 165, 233, 0.18);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.45);
        font-weight: 700;
    }

    QPushButton.ActionBtn {
        background-color: rgba(30, 41, 59, 0.65);
        color: #cbd5e1;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 6px 14px;
        font-weight: 600;
        font-size: 12px;
    }

    QPushButton.ActionBtn:hover {
        background-color: rgba(51, 65, 85, 0.85);
        color: #38bdf8;
        border-color: rgba(56, 189, 248, 0.35);
    }

    QPushButton.ActionBtn:checked {
        background-color: rgba(14, 165, 233, 0.2);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.5);
        font-weight: 700;
    }

    QLineEdit {
        background-color: rgba(15, 23, 42, 0.7);
        color: #f8fafc;
        border: 1px solid rgba(255, 255, 255, 0.09);
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 12px;
    }

    QLineEdit:focus {
        border: 1px solid #38bdf8;
        background-color: rgba(15, 23, 42, 0.9);
    }

    QToolTip {
        background-color: #0b101b;
        color: #f8fafc;
        border: 1px solid rgba(56, 189, 248, 0.3);
        padding: 6px 10px;
        border-radius: 7px;
        font-size: 11px;
    }
    """

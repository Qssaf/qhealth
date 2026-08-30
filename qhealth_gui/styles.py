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
        background: rgba(255, 255, 255, 0.28);
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    /* Production-Grade Dark Glass Cards */
    QFrame.GlassCard {
        background-color: rgba(13, 18, 29, 0.82);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
    }

    QFrame.GlassCardInner {
        background-color: rgba(10, 14, 23, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 10px;
    }

    /* Segmented Navigation Buttons */
    QPushButton.TabBtn {
        background-color: transparent;
        color: #94a3b8;
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 6px 14px;
        font-weight: 600;
        font-size: 12px;
    }

    QPushButton.TabBtn:hover {
        color: #f8fafc;
        background-color: rgba(255, 255, 255, 0.06);
    }

    QPushButton.TabBtn:checked {
        background-color: rgba(16, 185, 129, 0.16);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.35);
    }

    QPushButton.ActionBtn {
        background-color: rgba(30, 41, 59, 0.85);
        color: #e2e8f0;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 6px 13px;
        font-weight: 600;
        font-size: 12px;
    }

    QPushButton.ActionBtn:hover {
        background-color: rgba(51, 65, 85, 0.95);
        color: #ffffff;
        border-color: rgba(255, 255, 255, 0.22);
    }

    QPushButton.ActionBtn:checked {
        background-color: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.4);
    }

    /* Search & LineEdit */
    QLineEdit {
        background-color: rgba(10, 14, 23, 0.9);
        color: #f8fafc;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 12px;
    }

    QLineEdit:focus {
        border: 1px solid #10b981;
        background-color: rgba(13, 18, 29, 0.95);
    }

    /* Tooltips */
    QToolTip {
        background-color: #0b101b;
        color: #f8fafc;
        border: 1px solid rgba(255, 255, 255, 0.18);
        padding: 6px 10px;
        border-radius: 7px;
        font-size: 11px;
    }
    """

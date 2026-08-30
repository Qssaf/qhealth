def get_qhealth_stylesheet() -> str:
    return """
    QMainWindow {
        background-color: #0a0d14;
        color: #f1f5f9;
    }

    QWidget {
        font-family: 'Inter', 'Noto Sans', 'Segoe UI', sans-serif;
        font-size: 13px;
        color: #e2e8f0;
    }

    QScrollArea {
        border: none;
        background-color: transparent;
    }

    QScrollBar:vertical {
        border: none;
        background: rgba(15, 23, 42, 0.5);
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
        background: rgba(255, 255, 255, 0.25);
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }

    /* Glass Cards */
    QFrame.GlassCard {
        background-color: rgba(15, 23, 42, 0.75);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
    }

    QFrame.GlassCardInner {
        background-color: rgba(10, 13, 20, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 10px;
    }

    /* Buttons */
    QPushButton.TabBtn {
        background-color: transparent;
        color: #94a3b8;
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 6px 16px;
        font-weight: 600;
        font-size: 13px;
    }

    QPushButton.TabBtn:hover {
        color: #f8fafc;
        background-color: rgba(255, 255, 255, 0.05);
    }

    QPushButton.TabBtn:checked {
        background-color: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }

    QPushButton.ActionBtn {
        background-color: rgba(30, 41, 59, 0.8);
        color: #e2e8f0;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 6px 14px;
        font-weight: 600;
        font-size: 12px;
    }

    QPushButton.ActionBtn:hover {
        background-color: rgba(51, 65, 85, 0.9);
        color: #ffffff;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }

    QPushButton.ActionBtn:checked {
        background-color: rgba(245, 158, 11, 0.2);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.4);
    }

    /* Inputs */
    QLineEdit {
        background-color: rgba(10, 13, 20, 0.8);
        color: #f8fafc;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 12px;
    }

    QLineEdit:focus {
        border: 1px solid #10b981;
    }

    /* Date Edit */
    QDateEdit {
        background-color: rgba(10, 13, 20, 0.8);
        color: #f8fafc;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 5px 10px;
        font-size: 12px;
        font-family: monospace;
    }

    QDateEdit::drop-down {
        border: none;
        width: 16px;
    }

    /* Tooltips */
    QToolTip {
        background-color: #0f172a;
        color: #f8fafc;
        border: 1px solid rgba(255, 255, 255, 0.15);
        padding: 6px 10px;
        border-radius: 6px;
    }
    """

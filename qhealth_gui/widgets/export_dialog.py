import os
import datetime
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QFileDialog, QMessageBox, QComboBox
)
from qhealth_core.db import export_data_to_csv, export_data_to_json

class ExportDialog(QDialog):
    def __init__(self, current_range: str = "all_time", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export QHealth Data")
        self.setFixedSize(460, 360)
        self.setStyleSheet("""
            QDialog {
                background-color: #0c1017;
                color: #f1f5f9;
            }
            QFrame#DialogContainer {
                background-color: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 14px;
            }
            QRadioButton {
                color: #e2e8f0;
                font-size: 13px;
                font-weight: 600;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 1.5px solid #64748b;
                background-color: #0b101b;
            }
            QRadioButton::indicator:checked {
                background-color: #10b981;
                border: 2px solid #34d399;
            }
            QComboBox {
                background-color: rgba(30, 41, 59, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #ffffff;
                selection-background-color: rgba(16, 185, 129, 0.3);
            }
        """)

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(16, 16, 16, 16)

        container = QFrame()
        container.setObjectName("DialogContainer")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        # Title
        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        title = QLabel("EXPORT ACTIVITY DATA")
        title.setStyleSheet("font-size: 13px; font-weight: 800; color: #ffffff; letter-spacing: 0.5px;")
        sub = QLabel("Choose format and date range to export your data")
        sub.setStyleSheet("font-size: 11px; color: #64748b;")
        t_box.addWidget(title)
        t_box.addWidget(sub)
        lay.addLayout(t_box)

        # 1. Format Selection
        fmt_box = QVBoxLayout()
        fmt_box.setSpacing(8)
        fmt_lbl = QLabel("EXPORT FORMAT")
        fmt_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        fmt_box.addWidget(fmt_lbl)

        self.btn_csv = QRadioButton("CSV Spreadsheet (.csv) — Compatible with Excel & Sheets")
        self.btn_csv.setChecked(True)
        self.btn_json = QRadioButton("Full JSON Backup (.json) — Complete database archive")

        fmt_box.addWidget(self.btn_csv)
        fmt_box.addWidget(self.btn_json)
        lay.addLayout(fmt_box)

        # 2. Time Range Selection
        range_box = QVBoxLayout()
        range_box.setSpacing(6)
        r_lbl = QLabel("TIME RANGE")
        r_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #94a3b8; letter-spacing: 0.5px;")
        range_box.addWidget(r_lbl)

        self.range_combo = QComboBox()
        self.range_combo.addItem("All Time (Entire History)", "all_time")
        self.range_combo.addItem("Last 30 Days", "month")
        self.range_combo.addItem("Last 7 Days", "week")
        self.range_combo.addItem("Today", "day")
        
        # Set default index
        idx = self.range_combo.findData(current_range)
        if idx >= 0:
            self.range_combo.setCurrentIndex(idx)
        range_box.addWidget(self.range_combo)
        lay.addLayout(range_box)

        lay.addStretch()

        # Action Buttons (Cancel / Export)
        btn_lay = QHBoxLayout()
        btn_lay.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setProperty("class", "ActionBtn")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_export = QPushButton("💾 Export File...")
        self.btn_export.setProperty("class", "ActionBtn")
        self.btn_export.setStyleSheet("background-color: #10b981; color: #ffffff; font-weight: 700; border: none;")
        self.btn_export.clicked.connect(self._do_export)

        btn_lay.addStretch()
        btn_lay.addWidget(self.btn_cancel)
        btn_lay.addWidget(self.btn_export)
        lay.addLayout(btn_lay)

        main_lay.addWidget(container)

    def _do_export(self):
        is_csv = self.btn_csv.isChecked()
        range_code = self.range_combo.currentData()

        today_str = datetime.date.today().strftime("%Y-%m-%d")
        default_name = f"qhealth_export_{range_code}_{today_str}.{'csv' if is_csv else 'json'}"
        default_path = os.path.expanduser(f"~/Downloads/{default_name}")

        filter_str = "CSV Files (*.csv)" if is_csv else "JSON Files (*.json)"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Export File", default_path, filter_str)

        if not file_path:
            return

        try:
            if is_csv:
                export_data_to_csv(file_path, range_type=range_code)
            else:
                export_data_to_json(file_path)

            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported data to:\n{file_path}"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Could not export file:\n{str(e)}"
            )

"""Theme utilities for applying dark theme and size-based coloring."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QStyleFactory, QTableWidgetItem

# Type tag colors - single source of truth
TYPE_COLORS = {
    "AUR": "#ff7b72",
    "repo": "#7ee787",
    "cache": "#d2a8ff",
    "flatpak": "#79c0ff",
    "broken": "#ff7b72",
    "aur-dep": "#ffab70",
    "aur-cache": "#79c0ff",
    "proton-prefix": "#ff7b72",
    "steam-runtime": "#d2a8ff",
    "ollama": "#79c0ff",
    "launcher-runner": "#ffab70",
    "npm-cache": "#d2a8ff",
    "npm-stale": "#ff7b72",
}


def get_type_color(tag: str) -> QColor:
    """Get QColor for a package type tag."""
    return QColor(TYPE_COLORS.get(tag, "#9e9e9e"))


def size_color(size: int) -> QColor:
    if size > 100 * 1024 * 1024:
        return QColor("#f97583")
    if size > 10 * 1024 * 1024:
        return QColor("#ffab70")
    return QColor("#7ee787")


class NumericTableItem(QTableWidgetItem):
    """Table widget item that sorts numerically based on stored integer size."""

    def __lt__(self, other):
        if other is None:
            return False
        a = self.data(Qt.UserRole)
        b = other.data(Qt.UserRole)
        if a is not None and b is not None:
            return a < b
        return False


def apply_dark_theme(app):
    app.setStyle(QStyleFactory.create("Fusion"))

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#1e1e1e"))
    palette.setColor(QPalette.WindowText, QColor("#e0e0e0"))
    palette.setColor(QPalette.Base, QColor("#252526"))
    palette.setColor(QPalette.AlternateBase, QColor("#2b2b2b"))
    palette.setColor(QPalette.ToolTipBase, QColor("#2d2d2d"))
    palette.setColor(QPalette.ToolTipText, QColor("#e0e0e0"))
    palette.setColor(QPalette.Text, QColor("#e0e0e0"))
    palette.setColor(QPalette.Button, QColor("#333333"))
    palette.setColor(QPalette.ButtonText, QColor("#e0e0e0"))
    palette.setColor(QPalette.BrightText, QColor("#ff7b72"))
    palette.setColor(QPalette.Link, QColor("#58a6ff"))
    palette.setColor(QPalette.Highlight, QColor("#264f78"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#6e6e6e"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#6e6e6e"))
    app.setPalette(palette)

    app.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #1e1e1e;
            color: #e0e0e0;
        }
        QTableWidget {
            background-color: #252526;
            alternate-background-color: #2b2b2b;
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            gridline-color: #3c3c3c;
            outline: none;
        }
        QTableWidget::item {
            padding: 2px 4px;
        }
        QTableWidget::item:selected {
            background-color: #264f78;
        }
        QHeaderView::section {
            background-color: #2d2d2d;
            color: #c0c0c0;
            padding: 4px 6px;
            border: none;
            border-bottom: 1px solid #3c3c3c;
            border-right: 1px solid #3c3c3c;
            font-weight: 600;
        }
        QHeaderView::section:hover {
            background-color: #353535;
        }
        QStatusBar {
            background-color: #252526;
            border-top: 1px solid #3c3c3c;
            color: #9e9e9e;
            font-size: 12px;
        }
        QPushButton {
            min-height: 32px;
            padding: 4px 18px;
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            font-size: 13px;
            font-weight: 500;
        }
        QPushButton:hover {
            border-color: #5a5a5a;
        }
        QPushButton:pressed {
            background-color: #3c3c3c;
        }
        QPushButton:disabled {
            color: #6e6e6e;
            border-color: #333333;
        }
        QPushButton[class="danger"] {
            background-color: #7d1f1f;
            border-color: #a83a3a;
            color: #ffffff;
        }
        QPushButton[class="danger"]:hover {
            background-color: #9a2a2a;
        }
        QPushButton[class="danger"]:disabled {
            background-color: #3a1a1a;
            border-color: #3a2a2a;
            color: #6e4e4e;
        }
        QPushButton[class="primary"] {
            background-color: #1a4f8a;
            border-color: #2a6ab5;
            color: #ffffff;
        }
        QPushButton[class="primary"]:hover {
            background-color: #2065aa;
        }
        QPushButton[class="primary"]:disabled {
            background-color: #1a2a3a;
            border-color: #2a3a4a;
            color: #5e6e7e;
        }
        QPushButton[class="default"] {
            background-color: #333333;
            color: #e0e0e0;
        }
        QPushButton[class="default"]:hover {
            background-color: #3e3e3e;
        }
        QScrollBar:vertical {
            background-color: #252526;
            width: 10px;
            border: none;
        }
        QScrollBar::handle:vertical {
            background-color: #4a4a4a;
            border-radius: 5px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #5a5a5a;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        QCheckBox {
            spacing: 4px;
        }
        QMessageBox {
            background-color: #1e1e1e;
        }
        QMessageBox QLabel {
            color: #e0e0e0;
        }
        QMessageBox QPushButton {
            min-width: 80px;
        }
        /* Warning banner */
        QLabel[class="warning"] {
            background-color: #3a2a00;
            color: #ffcc66;
            padding: 8px 12px;
            border-radius: 4px;
            border: 1px solid #5a4a00;
            font-size: 12px;
            font-weight: 500;
        }
        /* Mode label */
        QLabel[class="mode-label"] {
            color: #a0a0a0;
            font-size: 13px;
        }
        /* Search input */
        QLineEdit[class="search"] {
            background-color: #252526;
            color: #e0e0e0;
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 13px;
        }
        QLineEdit[class="search"]:focus {
            border-color: #58a6ff;
        }
        /* Mode combo */
        QComboBox[class="mode-combo"] {
            background-color: #252526;
            color: #e0e0e0;
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 13px;
            min-width: 180px;
        }
        QComboBox[class="mode-combo"]::drop-down {
            border: none;
        }
        QComboBox[class="mode-combo"] QAbstractItemView {
            background-color: #252526;
            color: #e0e0e0;
            selection-background-color: #264f78;
        }
        /* Header checkbox */
        QCheckBox[class="header-checkbox"] {
            background: transparent;
        }
        QCheckBox[class="header-checkbox"]::indicator {
            width: 18px;
            height: 18px;
            border: 1px solid #5a5a5a;
            border-radius: 3px;
            background-color: #2d2d2d;
        }
        QCheckBox[class="header-checkbox"]::indicator:checked {
            background-color: #264f78;
            border-color: #58a6ff;
        }
        QCheckBox[class="header-checkbox"]::indicator:unchecked {
            background-color: #2d2d2d;
        }
        /* Filter chips */
        QLabel[class="filter-chip"] {
            background-color: #3d3d3d;
            color: #e0e0e0;
            border: 1px solid #58a6ff;
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 11px;
        }
        /* Progress dialogs */
        QProgressDialog {
            background-color: #1e1e1e;
            color: #e0e0e0;
        }
        QProgressBar {
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            background-color: #252526;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #58a6ff;
            border-radius: 3px;
        }
        /* Dialog tables */
        QDialog QTableWidget {
            background-color: #252526;
            alternate-background-color: #2b2b2b;
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            gridline-color: #3c3c3c;
        }
        QDialog QHeaderView::section {
            background-color: #2d2d2d;
            color: #c0c0c0;
            padding: 4px 6px;
            border: none;
            border-bottom: 1px solid #3c3c3c;
            border-right: 1px solid #3c3c3c;
            font-weight: 600;
        }
        /* Dep warning label */
        QLabel[class="dep-warning"] {
            background-color: #3a2a00;
            color: #ffcc66;
            padding: 8px;
            border-radius: 4px;
        }
        /* Removal details header */
        QLabel[class="removal-header"] {
            font-size: 14px;
            font-weight: 600;
            color: #e0e0e0;
        }
        /* Total reclaimable label */
        QLabel[class="total-label"] {
            font-size: 13px;
            color: #7ee787;
            font-weight: 600;
        }
        /* History header */
        QLabel[class="history-header"] {
            font-size: 14px;
            font-weight: 600;
            color: #e0e0e0;
        }
    """)

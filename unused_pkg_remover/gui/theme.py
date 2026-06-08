from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QStyleFactory, QTableWidgetItem


def size_color(size: int) -> QColor:
    if size > 100 * 1024 * 1024:
        return QColor("#f97583")
    if size > 10 * 1024 * 1024:
        return QColor("#ffab70")
    return QColor("#7ee787")


class NumericTableItem(QTableWidgetItem):
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
    """)

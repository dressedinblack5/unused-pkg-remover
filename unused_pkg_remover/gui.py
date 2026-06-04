import subprocess
import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QMessageBox, QStatusBar, QAbstractItemView, QStyleFactory,
    QProgressDialog, QLabel
)
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QColor, QPalette
from .scanner import get_unused_packages, FILTERED_COUNT

IGNORE_FILE = Path.cwd() / ".unused-ignore"

COL_SELECT = 0
COL_NAME = 1
COL_SIZE = 2
COL_TYPE = 3
COL_DESC = 4


def format_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}PB"


def size_color(size):
    if size > 100 * 1024 * 1024:
        return QColor("#f97583")
    if size > 10 * 1024 * 1024:
        return QColor("#ffab70")
    return QColor("#7ee787")


class OrphanCleaner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.packages = []
        self.setWindowTitle("Unused Package Remover")
        self.setMinimumSize(800, 400)
        self.resize(900, 500)
        self._setup_ui()
        self._load_settings()
        self._load_packages()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.warning = QLabel(
            "\u26A0  Always verify packages before removal. "
            "Some orphans may still be required by your system or workflow."
        )
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("""
            QLabel {
                background-color: #3a2a00;
                color: #ffcc66;
                padding: 8px 12px;
                border-radius: 4px;
                border: 1px solid #5a4a00;
                font-size: 12px;
                font-weight: 500;
            }
        """)
        layout.addWidget(self.warning)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["", "Package", "Size", "Type", "Description"])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(COL_SELECT, QHeaderView.Fixed)
        self.table.setColumnWidth(COL_SELECT, 40)
        hdr.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        self.table.setColumnWidth(COL_NAME, 200)
        hdr.setSectionResizeMode(COL_SIZE, QHeaderView.Fixed)
        self.table.setColumnWidth(COL_SIZE, 90)
        hdr.setSectionResizeMode(COL_TYPE, QHeaderView.Fixed)
        self.table.setColumnWidth(COL_TYPE, 60)
        hdr.setSectionResizeMode(COL_DESC, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(26)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.setProperty("class", "danger")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_remove.setEnabled(False)

        self.btn_ignore = QPushButton("Add to Ignore")
        self.btn_ignore.setProperty("class", "primary")
        self.btn_ignore.clicked.connect(self._add_to_ignore)
        self.btn_ignore.setEnabled(False)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setProperty("class", "default")
        self.btn_refresh.clicked.connect(self._load_packages)

        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_ignore)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_refresh)
        layout.addLayout(btn_row)

        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")
        layout.addWidget(self.status_bar)

        self.table.itemChanged.connect(self._on_item_changed)

    def _load_settings(self):
        s = QSettings("unused-pkg-remover", "unused-pkg-remover")
        geo = s.value("geometry")
        if geo:
            self.restoreGeometry(geo)

    def _save_settings(self):
        s = QSettings("unused-pkg-remover", "unused-pkg-remover")
        s.setValue("geometry", self.saveGeometry())

    def closeEvent(self, event):
        self._save_settings()
        event.accept()

    def _load_packages(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        from . import scanner as _sc
        _sc.FILTERED_COUNT = 0
        self.packages = get_unused_packages()
        filtered = _sc.FILTERED_COUNT
        self.table.setRowCount(len(self.packages))

        total_size = 0

        for i, pkg in enumerate(self.packages):
            total_size += pkg['size']

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Unchecked)
            chk.setData(Qt.UserRole, i)
            self.table.setItem(i, COL_SELECT, chk)

            name_item = QTableWidgetItem(pkg['name'])
            name_item.setToolTip(pkg['name'])
            self.table.setItem(i, COL_NAME, name_item)

            size_str = format_size(pkg['size'])
            size_item = QTableWidgetItem(size_str)
            size_item.setForeground(size_color(pkg['size']))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setData(Qt.UserRole, pkg['size'])
            self.table.setItem(i, COL_SIZE, size_item)

            type_item = QTableWidgetItem("AUR" if pkg['is_aur'] else "repo")
            type_item.setForeground(QColor("#ff7b72") if pkg['is_aur'] else QColor("#7ee787"))
            self.table.setItem(i, COL_TYPE, type_item)

            desc = pkg['desc']
            desc_item = QTableWidgetItem(desc[:120] + '...' if len(desc) > 120 else desc)
            desc_item.setToolTip(desc)
            self.table.setItem(i, COL_DESC, desc_item)

        self.table.setSortingEnabled(True)

        total_str = format_size(total_size)
        parts = [f"{len(self.packages)} packages", f"{total_str} reclaimable"]
        if filtered:
            parts.append(f"{filtered} excluded")
        self.status_bar.showMessage(" \u00b7 ".join(parts))
        self._update_buttons()

    def _on_item_changed(self, item):
        if item.column() == COL_SELECT:
            self._update_buttons()

    def _update_buttons(self):
        count = self._checked_count()
        self.btn_remove.setEnabled(count > 0)
        self.btn_remove.setText(f"Remove Selected ({count})" if count else "Remove Selected")
        self.btn_ignore.setEnabled(count > 0)
        self.btn_ignore.setText(f"Add to Ignore ({count})" if count else "Add to Ignore")

    def _checked_count(self):
        c = 0
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_SELECT)
            if item and item.checkState() == Qt.Checked:
                c += 1
        return c

    def _checked_indices(self):
        idxs = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_SELECT)
            if item and item.checkState() == Qt.Checked:
                idx = item.data(Qt.UserRole)
                if idx is not None:
                    idxs.append(idx)
        return idxs

    def _checked_packages(self):
        return [self.packages[i] for i in self._checked_indices()]

    def _remove_selected(self):
        pkgs = self._checked_packages()
        if not pkgs:
            return

        sel_size = sum(p['size'] for p in pkgs)
        lines = "\n".join(
            f"  \u2022 {p['name']} ({format_size(p['size'])})"
            for p in pkgs
        )
        msg = (
            f"Remove {len(pkgs)} packages?\n\n"
            f"{lines}\n\n"
            f"Total: {format_size(sel_size)}"
        )
        confirm = QMessageBox.question(
            self, "Confirm Removal", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        names = [p['name'] for p in pkgs]

        progress = QProgressDialog(
            f"Removing {len(pkgs)} packages...", "", 0, 0, self
        )
        progress.setWindowTitle("Uninstalling")
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModal)
        progress.setStyleSheet("""
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
        """)
        progress.show()
        QApplication.processEvents()

        self.setEnabled(False)
        try:
            subprocess.run(
                ["pkexec", "pacman", "-Rns", "--noconfirm"] + names,
                check=True, capture_output=True, text=True
            )
            progress.setLabelText(
                f"Removed {len(pkgs)} packages. Refreshing..."
            )
            QApplication.processEvents()
            self._load_packages()
        except subprocess.CalledProcessError as e:
            progress.close()
            self.status_bar.showMessage("Removal failed or cancelled.")
            QMessageBox.warning(
                self, "Removal Failed",
                f"Failed to remove packages.\n\n{e.stderr or 'Unknown error'}"
            )
        except Exception as e:
            progress.close()
            self.status_bar.showMessage("Error during removal.")
            QMessageBox.warning(self, "Error", str(e))
        finally:
            progress.close()
            self.setEnabled(True)

    def _add_to_ignore(self):
        pkgs = self._checked_packages()
        if not pkgs:
            return

        names = [p['name'] for p in pkgs]
        with open(IGNORE_FILE, "a") as f:
            for name in names:
                f.write(f"{name}\n")

        removed_indices = set(self._checked_indices())
        self.packages = [
            p for i, p in enumerate(self.packages)
            if i not in removed_indices
        ]

        self.table.setSortingEnabled(False)
        row = 0
        while row < self.table.rowCount():
            item = self.table.item(row, COL_SELECT)
            if item:
                idx = item.data(Qt.UserRole)
                if idx in removed_indices:
                    self.table.removeRow(row)
                    continue
            row += 1
        self.table.setSortingEnabled(True)

        self._update_buttons()
        self.status_bar.showMessage(
            f"Added {len(names)} packages to {IGNORE_FILE}"
        )


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


def run_gui():
    app = QApplication(sys.argv)
    app.setApplicationName("Unused Package Remover")
    app.setOrganizationName("unused-pkg-remover")
    apply_dark_theme(app)
    win = OrphanCleaner()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QEventLoop, QObject, QPropertyAnimation, QSettings, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStatusBar,
    QStyleFactory,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .scanner import get_dependents, get_unused_packages

IGNORE_FILE = Path.cwd() / ".unused-ignore"
HISTORY_DIR = Path.home() / ".local" / "share" / "unused-pkg-remover"
HISTORY_FILE = HISTORY_DIR / "history.log"
BATCH_SIZE = 50

COL_SELECT = 0
COL_NAME = 1
COL_SIZE = 2
COL_TYPE = 3
COL_DESC = 4


def format_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
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


class NumericTableItem(QTableWidgetItem):
    def __lt__(self, other):
        if other is None:
            return False
        a = self.data(Qt.UserRole)
        b = other.data(Qt.UserRole)
        if a is not None and b is not None:
            return a < b
        return super().__lt__(other)


class RemovalWorker(QObject):
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, names, batch_size, force=False):
        super().__init__()
        self.names = names
        self.batch_size = batch_size
        self.force = force

    def run(self):
        try:
            num_batches = (len(self.names) + self.batch_size - 1) // self.batch_size
            base = (
                ["pkexec", "pacman", "-Rns", "--nodeps"]
                if self.force
                else ["pkexec", "pacman", "-Rns"]
            )
            for i in range(0, len(self.names), self.batch_size):
                batch = self.names[i : i + self.batch_size]
                batch_num = i // self.batch_size + 1
                if num_batches > 1:
                    self.progress.emit(f"Removing batch {batch_num} of {num_batches}...")
                else:
                    self.progress.emit("Removing packages...")
                subprocess.run(
                    base + ["--noconfirm"] + batch,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            self.finished.emit(True, "")
        except subprocess.CalledProcessError as e:
            self.finished.emit(False, e.stderr or "Unknown error")
        except Exception as e:
            self.finished.emit(False, str(e))


class OrphanCleaner(QMainWindow):
    def __init__(self, dry_run=False, force_remove=False):
        super().__init__()
        self.packages = []
        self.dry_run = dry_run
        self.force_remove = force_remove
        self._last_filtered = 0
        self._removal_thread = None
        self._removal_worker = None
        self._removal_running = False
        self._force_attempted = False
        title = "Unused Package Remover"
        if dry_run:
            title = f"[DRY RUN] {title}"
        if force_remove:
            title = f"{title} (No Deps)"
        self.setWindowTitle(title)
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
            "\u26a0  Always verify packages before removal. "
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

        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search packages...")
        self.search.textChanged.connect(self._filter_packages)
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet("""
            QLineEdit {
                background-color: #252526;
                color: #e0e0e0;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #58a6ff;
            }
        """)
        search_row.addWidget(self.search, 1)

        layout.addLayout(search_row)

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

        container = QWidget()
        cb_layout = QHBoxLayout(container)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        cb_layout.setAlignment(Qt.AlignCenter)
        self.select_all_cb = QCheckBox(container)
        self.select_all_cb.stateChanged.connect(self._toggle_select_all)
        self.select_all_cb.setToolTip("Select / deselect all visible packages")
        cb_layout.addWidget(self.select_all_cb)
        hdr = self.table.horizontalHeader()
        hdr.setIndexWidget(hdr.model().index(0, COL_SELECT), container)

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

        self.btn_deselect = QPushButton("Deselect All")
        self.btn_deselect.setProperty("class", "default")
        self.btn_deselect.clicked.connect(self._deselect_all)
        self.btn_deselect.setEnabled(False)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setProperty("class", "default")
        self.btn_refresh.clicked.connect(self._load_packages)

        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_ignore)
        btn_row.addWidget(self.btn_deselect)
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

    def closeEvent(self, event):  # noqa: N802
        if self._removal_running:
            event.ignore()
            return
        self._save_settings()
        event.accept()

    def _load_packages(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.status_bar.showMessage("Updating list...")
        self.table.setEnabled(False)
        effect = QGraphicsOpacityEffect(self.table)
        self.table.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(120)
        anim.setStartValue(1.0)
        anim.setEndValue(0.25)
        loop = QEventLoop()
        anim.finished.connect(loop.quit)
        anim.start()
        loop.exec()

        try:
            self.packages, filtered = get_unused_packages()
        except RuntimeError as e:
            QMessageBox.critical(self, "Error", str(e))
            self.packages = []
            filtered = 0
        self.table.setRowCount(len(self.packages))

        for i, pkg in enumerate(self.packages):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Unchecked)
            chk.setData(Qt.UserRole, i)
            self.table.setItem(i, COL_SELECT, chk)

            name_item = QTableWidgetItem(pkg["name"])
            name_item.setToolTip(pkg["name"])
            self.table.setItem(i, COL_NAME, name_item)

            size_str = format_size(pkg["size"])
            size_item = NumericTableItem(size_str)
            size_item.setForeground(size_color(pkg["size"]))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setData(Qt.UserRole, pkg["size"])
            self.table.setItem(i, COL_SIZE, size_item)

            type_item = QTableWidgetItem("AUR" if pkg["is_aur"] else "repo")
            type_item.setForeground(QColor("#ff7b72") if pkg["is_aur"] else QColor("#7ee787"))
            self.table.setItem(i, COL_TYPE, type_item)

            desc = pkg["desc"]
            desc_item = QTableWidgetItem(desc[:120] + "..." if len(desc) > 120 else desc)
            desc_item.setToolTip(desc)
            self.table.setItem(i, COL_DESC, desc_item)

        self.table.setSortingEnabled(True)

        effect2 = QGraphicsOpacityEffect(self.table)
        self.table.setGraphicsEffect(effect2)
        anim2 = QPropertyAnimation(effect2, b"opacity")
        anim2.setDuration(120)
        anim2.setStartValue(0.25)
        anim2.setEndValue(1.0)
        loop2 = QEventLoop()
        anim2.finished.connect(loop2.quit)
        anim2.finished.connect(lambda: self.table.setEnabled(True))
        anim2.start()
        loop2.exec()

        self.table.setGraphicsEffect(None)

        self._last_filtered = filtered
        self._update_status_bar(filtered=filtered)
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
        self.btn_deselect.setEnabled(count > 0)
        self._update_checkbox_state()

    def _update_status_bar(self, filtered=None):
        if filtered is None:
            filtered = self._last_filtered
        total_size = sum(p["size"] for p in self.packages)
        total_str = format_size(total_size)
        parts = [f"{len(self.packages)} packages", f"{total_str} reclaimable"]
        if filtered:
            parts.append(f"{filtered} excluded")
        self.status_bar.showMessage(" \u00b7 ".join(parts))

    def _filter_packages(self, text):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_NAME)
            if item:
                visible = text.lower() in item.text().lower() if text else True
                self.table.setRowHidden(row, not visible)
        visible_count = sum(
            1 for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)
        )
        total = self.table.rowCount()
        if text:
            self.status_bar.showMessage(f"{visible_count} of {total} packages")
        else:
            self._update_status_bar()
        self._update_checkbox_state()

    def _toggle_select_all(self, state):
        checked = state == Qt.Checked
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                item = self.table.item(row, COL_SELECT)
                if item:
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_buttons()

    def _deselect_all(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_SELECT)
            if item:
                item.setCheckState(Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_buttons()

    def _update_checkbox_state(self):
        self.select_all_cb.blockSignals(True)
        visible = 0
        checked = 0
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                visible += 1
                item = self.table.item(row, COL_SELECT)
                if item and item.checkState() == Qt.Checked:
                    checked += 1
        if visible == 0 or checked == 0:
            self.select_all_cb.setCheckState(Qt.Unchecked)
        elif checked == visible:
            self.select_all_cb.setCheckState(Qt.Checked)
        else:
            self.select_all_cb.setCheckState(Qt.PartiallyChecked)
        self.select_all_cb.blockSignals(False)

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

    def _check_dependents(self, names):
        dependents = {}
        for name in names:
            deps = get_dependents(name)
            if deps:
                dependents[name] = deps
        return dependents

    def _remove_selected(self):
        if self._removal_running:
            return
        pkgs = self._checked_packages()
        if not pkgs:
            return

        names = [p["name"] for p in pkgs]
        sel_size = sum(p["size"] for p in pkgs)

        dep_warning = ""
        dependents = self._check_dependents(names)
        if dependents:
            dep_lines = []
            for pkg, deps in dependents.items():
                dep_lines.append(f"  {pkg} \u2190 {', '.join(deps)}")
            dep_warning = (
                "\u26a0  Some packages are required by others:\n"
                + "\n".join(dep_lines)
                + "\n\nRemoving them may break dependent packages.\n\n"
            )

        lines = "\n".join(f"  \u2022 {p['name']} ({format_size(p['size'])})" for p in pkgs)

        if self.dry_run:
            msg = (
                f"[DRY RUN] Would remove {len(pkgs)} packages\n\n"
                f"{dep_warning}"
                f"{lines}\n\n"
                f"Total: {format_size(sel_size)}"
            )
            QMessageBox.information(self, "Dry Run", msg)
            return

        msg = (
            f"Remove {len(pkgs)} packages?\n\n"
            f"{dep_warning}"
            f"{lines}\n\n"
            f"Total: {format_size(sel_size)}"
        )
        confirm = QMessageBox.question(
            self, "Confirm Removal", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        progress = QProgressDialog("Removing packages...", "", 0, 0, self)
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

        self.setEnabled(False)
        self._removal_pkgs = pkgs
        self._progress = progress
        self._removal_running = True

        self._removal_thread = QThread()
        self._removal_worker = RemovalWorker(names, BATCH_SIZE, force=self.force_remove)
        self._removal_worker.moveToThread(self._removal_thread)
        self._removal_thread.started.connect(self._removal_worker.run)
        self._removal_worker.progress.connect(progress.setLabelText)
        self._removal_worker.finished.connect(self._on_removal_finished)
        self._removal_thread.start()

    def _on_removal_finished(self, success, error_msg):
        self._progress.close()
        self.setEnabled(True)

        if success:
            HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            with open(HISTORY_FILE, "a") as f:
                from datetime import datetime

                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for pkg in self._removal_pkgs:
                    f.write(f"{ts} | REMOVED | {pkg['name']} | {format_size(pkg['size'])}\n")
            self._cleanup_thread()
            self._removal_running = False
            self._force_attempted = False
            self._load_packages()
        elif "could not satisfy dependencies" in error_msg:
            self._cleanup_thread()
            if self._force_attempted or self.force_remove:
                self._removal_running = False
                self._force_attempted = False
                QMessageBox.warning(
                    self,
                    "Force Removal Failed",
                    "Force removal also failed due to dependency conflicts.\n\n"
                    f"{error_msg}",
                )
            else:
                self._force_attempted = True
                self._handle_dep_conflict(error_msg)
        else:
            self.status_bar.showMessage("Removal failed or cancelled.")
            QMessageBox.warning(
                self, "Removal Failed", f"Failed to remove packages.\n\n{error_msg}"
            )
            self._cleanup_thread()
            self._removal_running = False
            self._force_attempted = False

    def _cleanup_thread(self):
        if self._removal_thread is not None:
            self._removal_thread.quit()
            self._removal_thread.wait(5000)
            self._removal_thread = None
        if self._removal_worker is not None:
            self._removal_worker = None

    def _handle_dep_conflict(self, error_msg):
        dep_lines = []
        removed = {p['name'] for p in self._removal_pkgs}
        involved = set()
        for line in error_msg.splitlines():
            ls = line.strip()
            if ls.startswith("::"):
                dep_lines.append(ls)
                for token in ls.split():
                    t = token.rstrip(",:")
                    if t in removed:
                        involved.add(t)

        dep_text = "\n".join(dep_lines) if dep_lines else error_msg
        prefix = ""
        if involved:
            prefix = f"Packages causing conflict: {', '.join(sorted(involved))}\n\n"
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Dependency Conflict")
        msg.setText("Some packages cannot be removed because others depend on them:")
        msg.setInformativeText(prefix + dep_text)
        msg.setDetailedText(error_msg)
        force_btn = msg.addButton("Force Remove (--nodeps)", QMessageBox.AcceptRole)
        msg.addButton(QMessageBox.Cancel)
        msg.exec()

        if msg.clickedButton() == force_btn:
            names = [p["name"] for p in self._removal_pkgs]
            progress = QProgressDialog("Force removing packages...", "", 0, 0, self)
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

            self.setEnabled(False)
            self._progress = progress

            self._removal_thread = QThread()
            self._removal_worker = RemovalWorker(names, BATCH_SIZE, force=True)
            self._removal_worker.moveToThread(self._removal_thread)
            self._removal_thread.started.connect(self._removal_worker.run)
            self._removal_worker.progress.connect(progress.setLabelText)
            self._removal_worker.finished.connect(self._on_removal_finished)
            self._removal_thread.start()
        else:
            self._removal_running = False
            self._force_attempted = False

    def _add_to_ignore(self):
        pkgs = self._checked_packages()
        if not pkgs:
            return

        names = [p["name"] for p in pkgs]
        with open(IGNORE_FILE, "a") as f:
            for name in names:
                f.write(f"{name}\n")

        self._load_packages()
        self.status_bar.showMessage(f"Added {len(names)} packages to {IGNORE_FILE}")


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


def run_gui(dry_run=False, force_remove=False):
    app = QApplication(sys.argv)
    app.setApplicationName("Unused Package Remover")
    app.setOrganizationName("unused-pkg-remover")
    apply_dark_theme(app)
    win = OrphanCleaner(dry_run=dry_run, force_remove=force_remove)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()

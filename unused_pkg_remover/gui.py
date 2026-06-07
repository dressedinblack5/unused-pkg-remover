import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import (
    QMutex,
    QObject,
    QPropertyAnimation,
    QSettings,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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

from .constants import format_size
from .scanner import (
    get_all_cache_packages,
    get_aur_build_deps,
    get_aur_cache_packages,
    get_broken_packages,
    get_cache_packages,
    get_dependents,
    get_obsolete_steam_runtimes,
    get_orphaned_proton_prefixes,
    get_stale_launcher_runners,
    get_unused_flatpaks,
    get_unused_packages,
)
from .services import (
    BATCH_SIZE,
    HISTORY_FILE,
    RemovalError,
    add_to_ignore,
    log_removal,
    remove_all_cache_packages,
    remove_aur_cache_packages,
    remove_aur_deps,
    remove_cache_packages,
    remove_flatpak_packages,
    remove_obsolete_steam_runtimes,
    remove_orphaned_proton_prefixes,
    remove_packages_batch,
    remove_stale_launcher_runners,
)

_SCAN_FUNCTIONS = {
    "orphans": get_unused_packages,
    "cache": lambda: (get_cache_packages(), 0),
    "all-cache": lambda: (get_all_cache_packages(), 0),
    "flatpak": lambda: (get_unused_flatpaks(), 0),
    "broken": lambda: (get_broken_packages(), 0),
    "aur-dep": lambda: (get_aur_build_deps(), 0),
    "aur-cache": lambda: (get_aur_cache_packages(), 0),
    "proton-prefix": lambda: (get_orphaned_proton_prefixes(), 0),
    "steam-runtime": lambda: (get_obsolete_steam_runtimes(), 0),
    "launcher-runner": lambda: (get_stale_launcher_runners(), 0),
}

_REMOVAL_ACTIONS = {
    "cache": ("Removing cached packages...", lambda w: remove_cache_packages(w.names)),
    "all-cache": ("Removing cached package files...", lambda w: remove_all_cache_packages(w.names)),
    "flatpak": ("Removing Flatpak runtimes...", lambda w: remove_flatpak_packages(w.names)),
    "aur-dep": ("Cleaning AUR build deps...", lambda _: remove_aur_deps()),
    "aur-cache": ("Removing AUR build sources...", lambda w: remove_aur_cache_packages(w.names)),
    "proton-prefix": (
        "Removing Proton prefixes...",
        lambda w: remove_orphaned_proton_prefixes(w.names),
    ),
    "steam-runtime": (
        "Removing Steam runtimes...",
        lambda w: remove_obsolete_steam_runtimes(w.names),
    ),
    "launcher-runner": (
        "Removing launcher runners...",
        lambda w: remove_stale_launcher_runners(w.names),
    ),
}

_AVAILABLE_MODES: list[tuple[str, str]] = [
    ("orphans", "Orphans"),
    ("cache", "Pacman Cache"),
    ("all-cache", "All Pacman Cache"),
]
if shutil.which("flatpak"):
    _AVAILABLE_MODES.append(("flatpak", "Flatpak Runtimes"))
_AVAILABLE_MODES.append(("broken", "Broken Packages"))
if shutil.which("yay") or shutil.which("paru"):
    _AVAILABLE_MODES.append(("aur-dep", "AUR Build Deps"))
_AVAILABLE_MODES.append(("aur-cache", "AUR Build Cache"))
_AVAILABLE_MODES.append(("proton-prefix", "Proton Prefixes"))
_AVAILABLE_MODES.append(("steam-runtime", "Steam Runtimes"))
_AVAILABLE_MODES.append(("launcher-runner", "Launcher Runners"))

IGNORE_FILE = Path.cwd() / ".unused-ignore"

COL_SELECT = 0
COL_NAME = 1
COL_SIZE = 2
COL_TYPE = 3
COL_DESC = 4

_PROGRESS_STYLE = """
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
"""


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


class ScanWorker(QObject):
    finished = Signal(object, int)  # packages list, filtered count
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, scan_mode: str) -> None:
        super().__init__()
        self.scan_mode = scan_mode
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            if self._cancelled:
                self.cancelled.emit()
                return
            func = _SCAN_FUNCTIONS.get(self.scan_mode)
            packages, filtered = func() if func else ([], 0)
            if self._cancelled:
                self.cancelled.emit()
                return
            self.finished.emit(packages, filtered)
        except Exception as e:
            self.error.emit(str(e))


class DependentsWorker(QObject):
    finished = Signal(dict)  # dict of pkg -> deps
    error = Signal(str)

    def __init__(self, names: list[str]) -> None:
        super().__init__()
        self.names = names
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            dependents = {}
            for name in self.names:
                if self._cancelled:
                    break
                deps = get_dependents(name)
                if deps:
                    dependents[name] = deps
            if not self._cancelled:
                self.finished.emit(dependents)
        except Exception as e:
            self.error.emit(str(e))


class RemovalWorker(QObject):
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(
        self, names: list[str], batch_size: int, force: bool = False, mode: str = "orphan"
    ) -> None:
        super().__init__()
        self.names = names
        self.batch_size = batch_size
        self.force = force
        self.mode = mode
        self._cancelled = False

    def run(self) -> None:
        try:
            if self.mode in _REMOVAL_ACTIONS:
                msg, action = _REMOVAL_ACTIONS[self.mode]
                self.progress.emit(msg)
                action(self)
            else:
                num_batches = (len(self.names) + self.batch_size - 1) // self.batch_size
                for i in range(0, len(self.names), self.batch_size):
                    if self._cancelled:
                        self.finished.emit(False, "Cancelled")
                        return
                    batch = self.names[i : i + self.batch_size]
                    batch_num = i // self.batch_size + 1
                    self.progress.emit(
                        f"Removing batch {batch_num} of {num_batches}..."
                        if num_batches > 1
                        else "Removing packages..."
                    )
                    remove_packages_batch(batch, self.force)
            self.finished.emit(True, "")
        except RemovalError as e:
            self.finished.emit(False, str(e))
        except Exception as e:
            self.finished.emit(False, str(e))


class OrphanCleaner(QMainWindow):
    def __init__(self, dry_run: bool = False, force_remove: bool = False) -> None:
        super().__init__()
        self.packages = []
        self.dry_run = dry_run
        self.force_remove = force_remove
        self._last_filtered = 0
        self._removal_thread = None
        self._removal_worker = None
        self._scan_thread = None
        self._scan_worker = None
        self._dep_thread = None
        self._dep_worker = None
        self._removal_running = False
        self._force_attempted = False
        self._loading = False
        self._scan_mode = "orphans"
        self._load_gen = 0
        self._mutex = QMutex()
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
        QTimer.singleShot(0, self._load_packages)

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

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_label = QLabel("Scan mode:")
        mode_label.setStyleSheet("color: #9e9e9e; font-size: 13px;")
        mode_row.addWidget(mode_label)
        self.mode_combo = QComboBox()
        self._mode_keys = [k for k, _ in _AVAILABLE_MODES]
        for _, label in _AVAILABLE_MODES:
            self.mode_combo.addItem(label)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.mode_combo.setStyleSheet("""
            QComboBox {
                background-color: #252526;
                color: #e0e0e0;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
                min-width: 180px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                color: #e0e0e0;
                selection-background-color: #264f78;
            }
        """)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

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

        self._select_all_row = None

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

        self.btn_history = QPushButton("History")
        self.btn_history.setProperty("class", "default")
        self.btn_history.clicked.connect(self._show_history)

        btn_row.addWidget(self.btn_remove)
        btn_row.addWidget(self.btn_ignore)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_deselect)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_history)
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
        self._cleanup_scan_thread()
        self._save_settings()
        event.accept()

    def _fade_table(self, start: float, end: float, callback):
        effect = QGraphicsOpacityEffect(self.table)
        self.table.setGraphicsEffect(effect)
        self._fade_anim = QPropertyAnimation(effect, b"opacity")
        self._fade_anim.setDuration(120)
        self._fade_anim.setStartValue(start)
        self._fade_anim.setEndValue(end)
        self._fade_anim.finished.connect(callback)
        self._fade_anim.start()

    def _load_packages(self):
        if self._removal_running or self._loading:
            return
        self._load_gen += 1
        self._cleanup_scan_thread()
        self._loading = True
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        mode_label = self.mode_combo.currentText()
        self.status_bar.showMessage(f"Scanning {mode_label.lower()}...")
        self.table.setEnabled(False)
        self._fade_table(1.0, 0.25, self._do_load_packages)

    def _on_mode_changed(self, index: int) -> None:
        self._scan_mode = self._mode_keys[index]
        self.btn_ignore.setVisible(self._scan_mode == "orphans")
        self._load_packages()

    def _do_load_packages(self):
        if self._scan_thread is not None:
            return

        slow_modes = {"broken", "flatpak", "all-cache", "aur-cache"}
        show_progress = self._scan_mode in slow_modes

        if show_progress:
            self._scan_progress = QProgressDialog(
                f"Scanning {self.mode_combo.currentText().lower()}...", "Cancel", 0, 0, self
            )
            self._scan_progress.setWindowTitle("Scanning")
            self._scan_progress.setMinimumDuration(0)
            self._scan_progress.setWindowModality(Qt.WindowModal)
            self._scan_progress.canceled.connect(self._cancel_scan)
            self._scan_progress.setStyleSheet(_PROGRESS_STYLE)
            self._scan_progress.show()

        self._scan_thread = QThread()
        self._scan_worker = ScanWorker(self._scan_mode)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.cancelled.connect(self._on_scan_cancelled)
        self._scan_thread.start()

    def _cancel_scan(self) -> None:
        if self._scan_worker is not None:
            self._scan_worker.cancel()

    def _on_scan_cancelled(self) -> None:
        self._cleanup_scan_thread()
        if hasattr(self, "_scan_progress") and self._scan_progress:
            self._scan_progress.close()
        self.status_bar.showMessage("Scan cancelled.")

    def _on_scan_finished(self, packages: list[dict], filtered: int) -> None:
        self._cleanup_scan_thread()
        if hasattr(self, "_scan_progress") and self._scan_progress:
            self._scan_progress.close()
        self.packages = packages

        row_count = len(self.packages) + 1  # +1 for select-all row
        self.table.setRowCount(row_count)
        self._select_all_row = 0

        type_colors = {
            "AUR": "#ff7b72",
            "repo": "#7ee787",
            "cache": "#d2a8ff",
            "flatpak": "#79c0ff",
            "broken": "#ff7b72",
            "aur-dep": "#ffab70",
            "aur-cache": "#79c0ff",
            "proton-prefix": "#ff7b72",
            "steam-runtime": "#d2a8ff",
            "launcher-runner": "#ffab70",
        }

        # Select-all header row
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Unchecked)
        chk.setData(Qt.UserRole, -1)
        self.table.setItem(0, COL_SELECT, chk)

        name_item = QTableWidgetItem("Select All")
        font = name_item.font()
        font.setBold(True)
        name_item.setFont(font)
        self.table.setItem(0, COL_NAME, name_item)

        desc_item = QTableWidgetItem("Check / uncheck all visible packages")
        desc_item.setToolTip("Check or uncheck all packages in the list")
        self.table.setItem(0, COL_DESC, desc_item)

        for i, pkg in enumerate(self.packages):
            row = i + 1
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Unchecked)
            chk.setData(Qt.UserRole, i)
            self.table.setItem(row, COL_SELECT, chk)

            name_item = QTableWidgetItem(pkg["name"])
            name_item.setToolTip(pkg["name"])
            self.table.setItem(row, COL_NAME, name_item)

            size_str = format_size(pkg["size"])
            size_item = NumericTableItem(size_str)
            size_item.setForeground(size_color(pkg["size"]))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setData(Qt.UserRole, pkg["size"])
            self.table.setItem(row, COL_SIZE, size_item)

            tag = pkg.get("type_tag", "AUR" if pkg.get("is_aur") else "repo")
            type_item = QTableWidgetItem(tag)
            type_item.setForeground(QColor(type_colors.get(tag, "#9e9e9e")))
            self.table.setItem(row, COL_TYPE, type_item)

            desc = pkg["desc"]
            desc_item = QTableWidgetItem(desc[:120] + "..." if len(desc) > 120 else desc)
            desc_item.setToolTip(desc)
            self.table.setItem(row, COL_DESC, desc_item)

        self.table.setSortingEnabled(True)
        self._fade_table(0.25, 1.0, lambda: self._finish_load(filtered))

    def _on_scan_error(self, msg: str) -> None:
        self._cleanup_scan_thread()
        QMessageBox.critical(self, "Scan Error", msg)
        self.packages = []
        filtered = 0
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)
        self._fade_table(1.0, 1.0, lambda: self._finish_load(filtered))

    def _cleanup_scan_thread(self) -> None:
        if self._scan_worker is not None:
            self._scan_worker.deleteLater()
        if self._scan_thread is not None:
            self._scan_thread.quit()
            self._scan_thread.wait(5000)
            self._scan_thread.deleteLater()
        self._scan_thread = None
        self._scan_worker = None

    def _finish_load(self, filtered):
        self._loading = False
        self.table.setGraphicsEffect(None)
        self.table.setEnabled(True)
        self._last_filtered = filtered
        self._update_status_bar(filtered=filtered)
        self._update_buttons()
        if self.search.text():
            self._filter_packages(self.search.text())

    def _on_item_changed(self, item):
        if item.column() == COL_SELECT:
            role = item.data(Qt.UserRole)
            if role == -1:
                checked = item.checkState() == Qt.Checked
                self.table.blockSignals(True)
                for row in range(1, self.table.rowCount()):
                    if not self.table.isRowHidden(row):
                        chk = self.table.item(row, COL_SELECT)
                        if chk:
                            chk.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                self.table.blockSignals(False)
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
        num = len(self.packages)
        parts = [f"{num} package{'s' if num != 1 else ''}", f"{total_str} reclaimable"]
        if filtered:
            parts.append(f"{filtered} excluded")
        self.status_bar.showMessage(" \u00b7 ".join(parts))

    def _filter_packages(self, text):
        for row in range(1, self.table.rowCount()):
            item = self.table.item(row, COL_NAME)
            if item:
                visible = text.lower() in item.text().lower() if text else True
                self.table.setRowHidden(row, not visible)
        self.table.setRowHidden(0, False)
        visible_count = sum(
            1 for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)
        )
        total = self.table.rowCount()
        if text:
            self.status_bar.showMessage(f"{visible_count} of {total} packages")
        else:
            self._update_status_bar()
        self._update_checkbox_state()

    def _deselect_all(self):
        self.table.blockSignals(True)
        for row in range(1, self.table.rowCount()):
            item = self.table.item(row, COL_SELECT)
            if item:
                item.setCheckState(Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_buttons()

    def _update_checkbox_state(self):
        visible_data = 0
        checked_data = 0
        for row in range(1, self.table.rowCount()):
            if not self.table.isRowHidden(row):
                visible_data += 1
                item = self.table.item(row, COL_SELECT)
                if item and item.checkState() == Qt.Checked:
                    checked_data += 1
        sel_item = self.table.item(0, COL_SELECT)
        if sel_item is not None:
            self.table.blockSignals(True)
            if visible_data == 0 or checked_data == 0:
                sel_item.setCheckState(Qt.Unchecked)
            elif checked_data == visible_data:
                sel_item.setCheckState(Qt.Checked)
            else:
                sel_item.setCheckState(Qt.PartiallyChecked)
            self.table.blockSignals(False)

    def _checked_count(self):
        c = 0
        for row in range(1, self.table.rowCount()):
            item = self.table.item(row, COL_SELECT)
            if item and item.checkState() == Qt.Checked:
                c += 1
        return c

    def _checked_indices(self):
        idxs = []
        for row in range(1, self.table.rowCount()):
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

    def _show_removal_details(
        self, pkgs: list[dict], total_size: int, dep_warning: str, dry_run: bool = False
    ) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle("Dry Run" if dry_run else "Confirm Removal")
        dialog.setMinimumSize(550, 400)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        header = QLabel(
            f"[DRY RUN] Would remove {len(pkgs)} packages"
            if dry_run
            else f"Remove {len(pkgs)} packages?"
        )
        header.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0;")
        layout.addWidget(header)

        if dep_warning:
            dep_label = QLabel(f"\u26a0  Dependency warnings:\n{dep_warning}")
            dep_label.setWordWrap(True)
            dep_label.setStyleSheet(
                "background-color: #3a2a00; color: #ffcc66; padding: 8px; border-radius: 4px;"
            )
            layout.addWidget(dep_label)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Package", "Size", "Type"])
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setRowCount(len(pkgs))
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(1, 90)
        table.setColumnWidth(2, 70)

        for i, pkg in enumerate(pkgs):
            table.setItem(i, 0, QTableWidgetItem(pkg["name"]))
            size_item = QTableWidgetItem(format_size(pkg["size"]))
            size_item.setForeground(size_color(pkg["size"]))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(i, 1, size_item)
            tag = pkg.get("type_tag", "AUR" if pkg.get("is_aur") else "repo")
            table.setItem(i, 2, QTableWidgetItem(tag))

        layout.addWidget(table)

        total_label = QLabel(f"Total reclaimable: {format_size(total_size)}")
        total_label.setStyleSheet("font-size: 13px; color: #7ee787; font-weight: 600;")
        layout.addWidget(total_label)

        buttons = QDialogButtonBox()
        if dry_run:
            buttons.setStandardButtons(QDialogButtonBox.Ok)
        else:
            buttons.addButton("Remove", QDialogButtonBox.AcceptRole)
            buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        return dialog.exec() == QDialog.Accepted

    def _remove_selected(self):
        if self._removal_running:
            return
        pkgs = self._checked_packages()
        if not pkgs:
            return

        names = [p["name"] for p in pkgs]
        sel_size = sum(p["size"] for p in pkgs)

        if self._scan_mode != "orphans":
            self._proceed_with_removal(pkgs, sel_size, {})
            return

        self._dep_check_pkgs = pkgs
        self._dep_check_size = sel_size
        self._dep_check_names = names

        self._dep_progress = QProgressDialog("Checking dependencies...", "Cancel", 0, 0, self)
        self._dep_progress.setWindowTitle("Dependency Check")
        self._dep_progress.setMinimumDuration(0)
        self._dep_progress.setWindowModality(Qt.WindowModal)
        self._dep_progress.canceled.connect(self._cancel_dependents_check)
        self._dep_progress.setStyleSheet(_PROGRESS_STYLE)
        self._dep_progress.show()

        self._dep_thread = QThread()
        self._dep_worker = DependentsWorker(names)
        self._dep_worker.moveToThread(self._dep_thread)
        self._dep_thread.started.connect(self._dep_worker.run)
        self._dep_worker.finished.connect(self._on_dependents_finished)
        self._dep_worker.error.connect(self._on_dependents_error)
        self._dep_thread.start()

    def _cancel_dependents_check(self) -> None:
        if self._dep_worker is not None:
            self._dep_worker.cancel()

    def _on_dependents_error(self, msg: str) -> None:
        self._cleanup_dependents_thread()
        QMessageBox.warning(self, "Dependency Check Failed", msg)
        self._proceed_with_removal(self._dep_check_pkgs, self._dep_check_size, {})

    def _on_dependents_finished(self, dependents: dict) -> None:
        self._cleanup_dependents_thread()
        dep_warning = ""
        if dependents:
            dep_lines = []
            for pkg, deps in dependents.items():
                dep_lines.append(f"{pkg} \u2190 {', '.join(deps)}")
            dep_warning = "\n".join(dep_lines)

        if self.dry_run:
            self._show_removal_details(
                self._dep_check_pkgs, self._dep_check_size, dep_warning, dry_run=True
            )
            return

        self._proceed_with_removal(self._dep_check_pkgs, self._dep_check_size, dep_warning)

    def _cleanup_dependents_thread(self) -> None:
        if self._dep_worker is not None:
            self._dep_worker.deleteLater()
        if self._dep_thread is not None:
            self._dep_thread.quit()
            self._dep_thread.wait(5000)
            self._dep_thread.deleteLater()
        self._dep_thread = None
        self._dep_worker = None
        if self._dep_progress:
            self._dep_progress.close()

    def _start_removal_thread(
        self, names: list[str], label: str, force: bool | None = None
    ) -> None:
        progress = QProgressDialog(label, "Cancel", 0, 0, self)
        progress.setWindowTitle("Uninstalling")
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModal)
        progress.canceled.connect(self._cancel_removal)
        progress.setStyleSheet(_PROGRESS_STYLE)
        progress.show()
        self.setEnabled(False)
        self._progress = progress
        self._removal_running = True
        self._removal_thread = QThread()
        self._removal_worker = RemovalWorker(
            names,
            BATCH_SIZE,
            force=force if force is not None else self.force_remove,
            mode=self._scan_mode,
        )
        self._removal_worker.moveToThread(self._removal_thread)
        self._removal_thread.started.connect(self._removal_worker.run)
        self._removal_worker.progress.connect(progress.setLabelText)
        self._removal_worker.finished.connect(self._on_removal_finished)
        self._removal_thread.start()

    def _proceed_with_removal(self, pkgs, sel_size, dep_warning):
        if not self._show_removal_details(pkgs, sel_size, dep_warning):
            return
        self._removal_pkgs = pkgs
        self._start_removal_thread([p["name"] for p in pkgs], "Removing packages...")

    def _on_removal_finished(self, success, error_msg):
        self._progress.close()
        self.setEnabled(True)

        if success:
            log_removal(self._removal_pkgs)
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
                    f"Force removal also failed due to dependency conflicts.\n\n{error_msg}",
                )
            else:
                self._force_attempted = True
                self._handle_dep_conflict(error_msg)
        elif error_msg == "Cancelled":
            self.status_bar.showMessage("Removal cancelled.")
            self._cleanup_thread()
            self._removal_running = False
            self._force_attempted = False
        else:
            self.status_bar.showMessage("Removal failed.")
            QMessageBox.warning(
                self, "Removal Failed", f"Failed to remove packages.\n\n{error_msg}"
            )
            self._cleanup_thread()
            self._removal_running = False
            self._force_attempted = False

    def _cleanup_thread(self):
        if self._removal_worker is not None:
            self._removal_worker.deleteLater()
        if self._removal_thread is not None:
            self._removal_thread.quit()
            self._removal_thread.wait(5000)
            self._removal_thread.deleteLater()
        self._removal_thread = None
        self._removal_worker = None

    def _handle_dep_conflict(self, error_msg):
        dep_lines = []
        removed = {p["name"] for p in self._removal_pkgs}
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
            self._start_removal_thread(
                [p["name"] for p in self._removal_pkgs], "Force removing packages...", force=True
            )
        else:
            self._removal_running = False
            self._force_attempted = False

    def _cancel_removal(self):
        self._mutex.lock()
        worker = self._removal_worker
        self._mutex.unlock()
        if worker is not None:
            worker._cancelled = True
        self.status_bar.showMessage("Cancelling removal...")

    def _add_to_ignore(self):
        if self._removal_running:
            return
        pkgs = self._checked_packages()
        if not pkgs:
            return

        names = [p["name"] for p in pkgs]
        reply = QMessageBox.question(
            self,
            "Add to Ignore",
            f"Add {len(names)} package(s) to {IGNORE_FILE}?\n\n"
            + "\n".join(f"  \u2022 {n}" for n in names[:20])
            + ("\n  ..." if len(names) > 20 else ""),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        add_to_ignore(IGNORE_FILE, names)

        self._load_packages()
        self.status_bar.showMessage(f"Added {len(names)} packages to {IGNORE_FILE}")

    def _show_history(self) -> None:
        if not HISTORY_FILE.exists():
            QMessageBox.information(self, "History", "No removal history found.")
            return

        entries = HISTORY_FILE.read_text().strip().splitlines()
        if not entries:
            QMessageBox.information(self, "History", "No removal history found.")
            return

        parsed = []
        for line in entries:
            parts = line.split(" | ")
            if len(parts) >= 3:
                parsed.append({"ts": parts[0], "name": parts[2], "raw": line})

        dialog = QDialog(self)
        dialog.setWindowTitle("Removal History")
        dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        header = QLabel(f"{len(parsed)} packages removed")
        header.setStyleSheet("font-size: 14px; font-weight: 600; color: #e0e0e0;")
        layout.addWidget(header)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Timestamp", "Package", "Action"])
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setRowCount(len(parsed))
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 180)

        for i, entry in enumerate(parsed):
            table.setItem(i, 0, QTableWidgetItem(entry["ts"]))
            table.setItem(i, 1, QTableWidgetItem(entry["name"]))
            table.setItem(i, 2, QTableWidgetItem("removed"))

        layout.addWidget(table)

        btn_layout = QHBoxLayout()
        btn_reinstall = QPushButton("Reinstall Selected")
        btn_reinstall.setProperty("class", "primary")
        btn_reinstall.clicked.connect(lambda: self._reinstall_from_history(table, parsed, dialog))
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        btn_layout.addWidget(btn_reinstall)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        dialog.exec()

    def _reinstall_from_history(
        self, table: QTableWidget, parsed: list[dict], dialog: QDialog
    ) -> None:
        selected = set()
        for item in table.selectedItems():
            row = item.row()
            selected.add(parsed[row]["name"])

        if not selected:
            QMessageBox.information(self, "Reinstall", "No packages selected.")
            return

        names = sorted(selected)
        confirm = QMessageBox.question(
            self,
            "Reinstall Packages",
            f"Reinstall {len(names)} packages?\n\n"
            + "\n".join(f"  \u2022 {n}" for n in names)
            + "\n\nThis will run: pacman -S <packages>",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        progress = QProgressDialog("Reinstalling packages...", None, 0, 0, self)
        progress.setWindowTitle("Reinstalling")
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModal)
        progress.setStyleSheet(_PROGRESS_STYLE)
        progress.show()

        try:
            subprocess.run(
                ["pkexec", "pacman", "-S", "--noconfirm"] + names,
                check=True,
                capture_output=True,
                text=True,
            )
            progress.close()
            QMessageBox.information(
                self, "Reinstall", f"Successfully reinstalled {len(names)} packages."
            )
            dialog.accept()
        except subprocess.CalledProcessError as e:
            progress.close()
            QMessageBox.warning(
                self, "Reinstall Failed", f"Failed to reinstall packages.\n\n{e.stderr or str(e)}"
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


def run_gui(dry_run: bool = False, force_remove: bool = False) -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Unused Package Remover")
    app.setOrganizationName("unused-pkg-remover")
    apply_dark_theme(app)
    win = OrphanCleaner(dry_run=dry_run, force_remove=force_remove)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()

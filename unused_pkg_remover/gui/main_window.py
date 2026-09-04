from PySide6.QtCore import QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from typing_extensions import override

from ..constants import format_size
from ..services import (
    BATCH_SIZE,
    HISTORY_FILE,
    RemovalError,
    add_to_ignore,
    log_removal,
    run_pkexec,
)
from .constants import (
    COL_DESC,
    COL_NAME,
    COL_SELECT,
    COL_SIZE,
    COL_TYPE,
    get_available_modes,
    get_ignore_file,
)
from .theme import NumericTableItem, get_type_color, size_color
from .workers import DependentsWorker, RemovalWorker, ScanWorker


class OrphanCleaner(QMainWindow):
    """Main window for scanning and removing unused packages."""

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
        self._scan_progress = None
        self._dep_progress = None
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

    def _setup_ui(self) -> None:
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
        self.warning.setProperty("class", "warning")
        layout.addWidget(self.warning)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_label = QLabel("Scan Mode:")
        mode_label.setProperty("class", "mode-label")
        mode_row.addWidget(mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.setProperty("class", "mode-combo")
        modes = get_available_modes()
        self._mode_keys = [k for k, _ in modes]
        for _, label in modes:
            self.mode_combo.addItem(label)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search packages...")
        self.search.textChanged.connect(self._filter_packages)
        self.search.setClearButtonEnabled(True)
        self.search.setProperty("class", "search")
        search_row.addWidget(self.search, 1)
        layout.addLayout(search_row)

        self.filter_chips_layout = QHBoxLayout()
        self.filter_chips_layout.setSpacing(5)
        self.filter_chips_layout.setAlignment(Qt.AlignLeft)
        layout.addLayout(self.filter_chips_layout)

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

        # Header checkbox for Select All
        self.header_checkbox = QCheckBox()
        self.header_checkbox.setFixedSize(24, 24)
        self.header_checkbox.setCursor(Qt.ArrowCursor)
        self.header_checkbox.setProperty("class", "header-checkbox")
        self.header_checkbox.clicked.connect(self._toggle_all_visible)
        self.header_checkbox.setParent(hdr)

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

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.search.setFocus)
        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(self._on_select_all)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self._remove_selected)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._on_escape)

        self.table.itemChanged.connect(self._on_item_changed)

    @override
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_header_checkbox_position()

    def _update_header_checkbox_position(self) -> None:
        hdr = self.table.horizontalHeader()
        x = (hdr.sectionSize(0) - self.header_checkbox.width()) // 2
        y = (hdr.height() - self.header_checkbox.height()) // 2
        self.header_checkbox.move(x, y)

    def _load_settings(self) -> None:
        s = QSettings("unused-pkg-remover", "unused-pkg-remover")
        geo = s.value("geometry")
        if geo:
            self.restoreGeometry(geo)

    def _save_settings(self) -> None:
        s = QSettings("unused-pkg-remover", "unused-pkg-remover")
        s.setValue("geometry", self.saveGeometry())

    def closeEvent(self, event):  # noqa: N802
        if self._removal_running:
            event.ignore()
            return
        self._cleanup_scan_thread()
        self._cleanup_dependents_thread()
        self._save_settings()
        event.accept()

    def _load_packages(self) -> None:
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
        self._do_load_packages()

    def _on_mode_changed(self, index: int) -> None:
        self._scan_mode = self._mode_keys[index]
        self.btn_ignore.setVisible(self._scan_mode == "orphans")
        self._update_filter_chips()
        self._load_packages()

    def _do_load_packages(self) -> None:
        if self._scan_thread is not None:
            return

        slow_modes = {"broken", "flatpak", "aur-cache"}
        show_progress = self._scan_mode in slow_modes

        if show_progress:
            self._scan_progress = QProgressDialog(
                f"Scanning {self.mode_combo.currentText().lower()}...", "Cancel", 0, 0, self
            )
            self._scan_progress.setWindowTitle("Scanning")
            self._scan_progress.setMinimumDuration(0)
            self._scan_progress.setWindowModality(Qt.WindowModal)
            self._scan_progress.canceled.connect(self._cancel_scan)
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
        if self._scan_progress is not None:
            self._scan_progress.close()
        self.status_bar.showMessage("Scan cancelled.")

    def _on_scan_finished(self, packages: list[dict], filtered: int) -> None:
        self._cleanup_scan_thread()
        if self._scan_progress is not None:
            self._scan_progress.close()
        self.packages = packages

        row_count = len(self.packages)
        self.table.setRowCount(row_count)

        for i, pkg in enumerate(self.packages):
            row = i
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
            type_item.setForeground(get_type_color(tag))
            self.table.setItem(row, COL_TYPE, type_item)

            desc = pkg["desc"]
            desc_item = QTableWidgetItem(desc[:120] + "..." if len(desc) > 120 else desc)
            desc_item.setToolTip(desc)
            self.table.setItem(row, COL_DESC, desc_item)

        self.table.setSortingEnabled(True)
        self._finish_load(filtered)

    def _on_scan_error(self, msg: str) -> None:
        self._cleanup_scan_thread()
        QMessageBox.critical(self, "Scan Error", msg)
        self.packages = []
        filtered = 0
        self.table.setRowCount(0)
        self.table.setSortingEnabled(True)
        self._finish_load(filtered)

    def _cleanup_qthread(self, thread_attr: str, worker_attr: str) -> None:
        worker = getattr(self, worker_attr, None)
        thread = getattr(self, thread_attr, None)
        if worker is not None:
            worker.cancel()
            worker.deleteLater()
        if thread is not None:
            thread.quit()
            thread.wait(2000)
            thread.deleteLater()
        setattr(self, thread_attr, None)
        setattr(self, worker_attr, None)

    def _cleanup_scan_thread(self) -> None:
        self._cleanup_qthread("_scan_thread", "_scan_worker")

    def _finish_load(self, filtered) -> None:
        self._loading = False
        self.table.setGraphicsEffect(None)
        self.table.setEnabled(True)
        self._last_filtered = filtered
        self._update_status_bar(filtered=filtered)
        self._update_buttons()
        if self.search.text():
            self._filter_packages(self.search.text())

    def _on_item_changed(self, item) -> None:
        if item.column() == COL_SELECT:
            self._update_buttons()

    def _update_buttons(self) -> None:
        count = self._checked_count()
        self.btn_remove.setEnabled(count > 0)
        if count:
            total_size = format_size(self._checked_size())
            self.btn_remove.setText(f"Remove ({count} \u2014 {total_size})")
        else:
            self.btn_remove.setText("Remove Selected")
        self.btn_ignore.setEnabled(count > 0)
        self.btn_ignore.setText(f"Add to Ignore ({count})" if count else "Add to Ignore")
        self.btn_deselect.setEnabled(count > 0)
        self._update_checkbox_state()

    def _checked_size(self) -> int:
        return sum(p["size"] for p in self._checked_packages())

    def _update_status_bar(self, filtered=None) -> None:
        if filtered is None:
            filtered = self._last_filtered
        total_size = sum(p["size"] for p in self.packages)
        total_str = format_size(total_size)
        num = len(self.packages)
        parts = [f"{num} package{'s' if num != 1 else ''}", f"{total_str} reclaimable"]
        if filtered:
            parts.append(f"{filtered} excluded")
        self.status_bar.showMessage(" \u00b7 ".join(parts))

    def _update_filter_chips(self) -> None:
        while self.filter_chips_layout.count():
            item = self.filter_chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        chips = []
        if self.search.text():
            chips.append(f"Search: {self.search.text()}")

        for chip_text in chips:
            chip = QLabel(chip_text)
            chip.setProperty("class", "filter-chip")
            self.filter_chips_layout.addWidget(chip)

    def _filter_packages(self, text) -> None:
        self._update_filter_chips()
        for row in range(0, self.table.rowCount()):
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

    def _deselect_all(self) -> None:
        self.table.blockSignals(True)
        for row in range(0, self.table.rowCount()):
            item = self.table.item(row, COL_SELECT)
            if item:
                item.setCheckState(Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_buttons()

    def _on_select_all(self) -> None:
        if self.search.hasFocus():
            return
        self.header_checkbox.setChecked(True)
        self._toggle_all_visible(True)

    def _toggle_all_visible(self, checked: bool = None) -> None:
        if checked is None:
            checked = self.header_checkbox.isChecked()

        self.table.blockSignals(True)
        for row in range(0, self.table.rowCount()):
            if not self.table.isRowHidden(row):
                item = self.table.item(row, COL_SELECT)
                if item:
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_buttons()

    def _on_escape(self) -> None:
        if self.search.text():
            self.search.clear()

    def _update_checkbox_state(self) -> None:
        visible_data = 0
        checked_data = 0
        for row in range(0, self.table.rowCount()):
            if not self.table.isRowHidden(row):
                visible_data += 1
                item = self.table.item(row, COL_SELECT)
                if item and item.checkState() == Qt.Checked:
                    checked_data += 1

        if visible_data == 0 or checked_data == 0:
            self.header_checkbox.setCheckState(Qt.Unchecked)
        elif checked_data == visible_data:
            self.header_checkbox.setCheckState(Qt.Checked)
        else:
            self.header_checkbox.setCheckState(Qt.PartiallyChecked)

    def _checked_count(self) -> int:
        c = 0
        for row in range(0, self.table.rowCount()):
            item = self.table.item(row, COL_SELECT)
            if item and item.checkState() == Qt.Checked:
                c += 1
        return c

    def _checked_indices(self) -> list[int]:
        idxs = []
        for row in range(0, self.table.rowCount()):
            item = self.table.item(row, COL_SELECT)
            if item and item.checkState() == Qt.Checked:
                idx = item.data(Qt.UserRole)
                if idx is not None:
                    idxs.append(idx)
        return idxs

    def _checked_packages(self) -> list[dict]:
        return [self.packages[i] for i in self._checked_indices()]

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
        header.setProperty("class", "removal-header")
        layout.addWidget(header)

        if dep_warning:
            dep_label = QLabel(f"\u26a0  Dependency warnings:\n{dep_warning}")
            dep_label.setWordWrap(True)
            dep_label.setProperty("class", "dep-warning")
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
        total_label.setProperty("class", "total-label")
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

    def _remove_selected(self) -> None:
        if self._removal_running:
            return
        pkgs = self._checked_packages()
        if not pkgs:
            return

        names = [p["name"] for p in pkgs]
        sel_size = sum(p["size"] for p in pkgs)

        if self._scan_mode != "orphans":
            if self.dry_run:
                self._show_removal_details(pkgs, sel_size, "", dry_run=True)
                return
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
        self._cleanup_qthread("_dep_thread", "_dep_worker")
        if self._dep_progress is not None:
            self._dep_progress.close()
            self._dep_progress = None

    def _start_removal_thread(
        self, names: list[str], label: str, force: bool | None = None
    ) -> None:
        progress = QProgressDialog(label, "Cancel", 0, 0, self)
        progress.setWindowTitle("Uninstalling")
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModal)
        progress.canceled.connect(self._cancel_removal)
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

    def _proceed_with_removal(self, pkgs, sel_size, dep_warning) -> None:
        if not self._show_removal_details(pkgs, sel_size, dep_warning):
            return
        self._removal_pkgs = pkgs
        self._start_removal_thread([p["name"] for p in pkgs], f"Removing {len(pkgs)} packages...")

    def _on_removal_finished(self, success, error_msg) -> None:
        if getattr(self, "_progress", None) is not None:
            self._progress.close()
            self._progress = None
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
            self._load_packages()

    def _cleanup_thread(self) -> None:
        self._cleanup_qthread("_removal_thread", "_removal_worker")

    def _handle_dep_conflict(self, error_msg) -> None:
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
                [p["name"] for p in self._removal_pkgs],
                f"Force removing {len(self._removal_pkgs)} packages...",
                force=True,
            )
        else:
            self._removal_running = False
            self._force_attempted = False

    def _cancel_removal(self) -> None:
        if self._removal_worker is not None:
            self._removal_worker.cancel()
        self.status_bar.showMessage("Cancelling removal...")

    def _show_context_menu(self, pos) -> None:
        item = self.table.itemAt(pos)
        if item is None:
            return
        row = item.row()
        sel_item = self.table.item(row, COL_SELECT)
        if sel_item is None:
            return
        pkg_idx = sel_item.data(Qt.UserRole)
        pkg = self.packages[pkg_idx]

        menu = QMenu(self)
        copy_action = menu.addAction("Copy package name")
        copy_action.triggered.connect(lambda: self._copy_to_clipboard(pkg["name"]))

        if self._scan_mode == "orphans":
            ignore_action = menu.addAction("Add to ignore list")
            ignore_action.triggered.connect(lambda: self._ignore_single(pkg["name"]))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _copy_to_clipboard(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.status_bar.showMessage(f"Copied '{text}' to clipboard")

    def _ignore_single(self, name: str) -> None:
        add_to_ignore(get_ignore_file(), [name])
        self.status_bar.showMessage(f"Added '{name}' to ignore list")

    def _add_to_ignore(self) -> None:
        if self._removal_running:
            return
        pkgs = self._checked_packages()
        if not pkgs:
            return

        names = [p["name"] for p in pkgs]
        ignore_file = get_ignore_file()
        reply = QMessageBox.question(
            self,
            "Add to Ignore",
            f"Add {len(names)} package(s) to {ignore_file}?\n\n"
            + "\n".join(f"  \u2022 {n}" for n in names[:20])
            + ("\n  ..." if len(names) > 20 else ""),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        add_to_ignore(ignore_file, names)

        self._load_packages()
        self.status_bar.showMessage(f"Added {len(names)} packages to {ignore_file}")

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
        header.setProperty("class", "history-header")
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
        progress.show()

        try:
            run_pkexec(["pkexec", "pacman", "-S", "--noconfirm"] + names)
            progress.close()
            QMessageBox.information(
                self, "Reinstall", f"Successfully reinstalled {len(names)} packages."
            )
            dialog.accept()
        except RemovalError as e:
            progress.close()
            QMessageBox.warning(self, "Reinstall Failed", str(e))

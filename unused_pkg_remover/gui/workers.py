from PySide6.QtCore import QObject, Signal

from ..scanner import get_dependents
from ..services import (
    RemovalError,
    remove_aur_cache_packages,
    remove_aur_deps,
    remove_cache_packages,
    remove_flatpak_packages,
    remove_obsolete_steam_runtimes,
    remove_ollama_models,
    remove_orphaned_proton_prefixes,
    remove_packages_batch,
    remove_stale_launcher_runners,
)
from .constants import _REMOVAL_LABELS, _SCAN_FUNCTIONS


class ScanWorker(QObject):
    finished = Signal(object, int)
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
    finished = Signal(dict)
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

    def cancel(self) -> None:
        self._cancelled = True

    def _run_nonorphan(self) -> None:
        m = self.mode
        self.progress.emit(_REMOVAL_LABELS.get(m, "Removing..."))
        if m == "cache":
            remove_cache_packages(self.names, cancel_check=lambda: self._cancelled)
        elif m == "all-cache":
            remove_cache_packages(self.names, exact=True, cancel_check=lambda: self._cancelled)
        elif m == "flatpak":
            remove_flatpak_packages(self.names)
        elif m == "aur-dep":
            remove_aur_deps()
        elif m == "aur-cache":
            remove_aur_cache_packages(self.names)
        elif m == "proton-prefix":
            remove_orphaned_proton_prefixes(self.names)
        elif m == "steam-runtime":
            remove_obsolete_steam_runtimes(self.names)
        elif m == "ollama":
            remove_ollama_models(self.names)
        elif m == "launcher-runner":
            remove_stale_launcher_runners(self.names)

    def run(self) -> None:
        try:
            if self.mode in _REMOVAL_LABELS:
                self._run_nonorphan()
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
                        else f"Removing {len(self.names)} packages..."
                    )
                    remove_packages_batch(batch, self.force, cancel_check=lambda: self._cancelled)
            self.finished.emit(True, "")
        except RemovalError as e:
            self.finished.emit(False, str(e))
        except Exception as e:
            self.finished.emit(False, str(e))

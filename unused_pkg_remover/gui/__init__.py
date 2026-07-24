"""GUI package initialization for unused-pkg-remover."""
import sys

from PySide6.QtWidgets import QApplication

from .main_window import OrphanCleaner
from .theme import NumericTableItem, apply_dark_theme, size_color


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

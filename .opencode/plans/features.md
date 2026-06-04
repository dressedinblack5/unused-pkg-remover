# Implementation Plan: 5 New Features

## Feature 4: expac not found check (scanner.py)

**File:** `unused_pkg_remover/scanner.py`

- Add `import shutil` at top
- In `get_unused_packages()`, before calling `expac`, check `shutil.which("expac")`
- If `None`, raise `RuntimeError("expac not found. Install it: sudo pacman -S expac")`
- The GUI will catch this in `_load_packages()` and show a `QMessageBox.warning()`

## Feature 6: --deep scan (scanner.py + gui.py)

**File:** `unused_pkg_remover/scanner.py`

- Add `deep=False` param to `get_unused_packages(deep=False)`
- When `deep=True`, use `["pacman", "-Qdq"]` instead of `["pacman", "-Qtdq"]`
- The `-t` flag filters out packages not required by any other package; dropping it catches deeper orphans

## Feature 5: argparse flags (main.py)

**File:** `unused_pkg_remover/main.py`

- Add `import argparse`
- In `main()`, create `ArgumentParser` with:
  - `--dry-run` (`store_true`): show what would be removed without executing
  - `--deep` (`store_true`): enable deep orphan scan
- Pass args: `run_gui(dry_run=args.dry_run, deep_scan=args.deep)`

## Feature 1: Search/filter bar (gui.py)

**File:** `unused_pkg_remover/gui.py`

- Add `from PySide6.QtWidgets import QLineEdit` to imports
- In `_setup_ui()`, add a `QLineEdit` with placeholder "Search packages..." between the warning label and the table
- Connect `textChanged` signal to a new `_filter_packages(text)` method
- `_filter_packages`: iterate all rows, `setRowHidden(row, False)` if name contains text (case-insensitive), else `True`
- Update status bar suffix: "N of M shown" when filter active
- Store `self._filter_text` for refresh persistence

## Feature 3: Dependents check (gui.py + scanner.py)

**File:** `unused_pkg_remover/scanner.py`

- Add `get_dependents(pkg_name)` function
- Try `shutil.which("pactree")` first:
  - If available: run `pactree -r <pkg>`, parse output, filter out the package itself
  - If not: run `pacman -Qi <pkg>`, parse "Required By" and "Optional For" lines
- Return list of dependent package names (may be empty)

**File:** `unused_pkg_remover/gui.py`

- Import `get_dependents` from scanner
- In `_remove_selected()`, before the confirmation dialog:
  - For each selected package, call `get_dependents(name)`
  - Collect all dependents, deduplicate
  - If any exist, prepend warning to confirmation message:
    "⚠ These packages depend on selected packages and may break:\n  • dep1\n  • dep2\n"

## Wire dry-run into GUI

**File:** `unused_pkg_remover/gui.py`

- `run_gui(dry_run=False, deep_scan=False)` signature
- `OrphanCleaner.__init__` accepts `dry_run`, `deep_scan`
- Store as `self.dry_run`, `self.deep_scan`
- If `self.deep_scan`: pass `deep=True` in `_load_packages()` → `get_unused_packages(deep=True)`
- In `_remove_selected()`:
  - If `self.dry_run`: skip `pkexec`, show `QMessageBox.information` with "Would remove: ..."
  - Add `[DRY RUN]` prefix to window title when active
- Pass `deep` from `_load_packages` to `get_unused_packages` via a new param

---

## Files Touched

| File | Changes |
|---|---|
| `scanner.py` | `import shutil`, `expac` check, `deep` param, `get_dependents()` |
| `main.py` | `argparse`, `--dry-run`, `--deep` flags, pass to `run_gui()` |
| `gui.py` | QLineEdit filter, deep scan wiring, dry-run UI, dependents warning |
| `README.md` | Document new CLI flags, search bar, deep scan, dependents check |

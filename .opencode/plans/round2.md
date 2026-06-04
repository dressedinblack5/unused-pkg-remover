# Round 2 Implementation Plan

## Feature 1: Select All / Deselect All — Header Checkbox (gui.py)

Add a checkbox in the table header (column 0) that toggles all package checkboxes.

**Changes in `gui.py`:**
- Create a simple `QWidget` with a `QCheckBox` centered in column 0 header
- Use `self.table.setCellWidget(0, 0, widget)` approach or subclass `QHeaderView`
- The checkbox `stateChanged` signal toggles visible rows:
  - Iterate all rows, skip hidden ones, set `checkState` to `Qt.Checked` or `Qt.Unchecked`
  - Update `_update_buttons()` after toggle
- When the header checkbox changes state, use `blockSignals` to prevent recursion from individual row `itemChanged` events
- Reflect the header checkbox state:
  - If all visible rows checked → checked
  - If some checked → partially checked (`Qt.PartiallyChecked`)
  - If none checked → unchecked
  - Update this in `_update_buttons()` or a dedicated method

## Feature 5: Removal History Log (gui.py)

Log removed packages with timestamp to `~/.local/share/unused-pkg-remover/history.log`.

**Changes in `gui.py`:**
- Add `HISTORY_DIR = Path.home() / ".local" / "share" / "unused-pkg-remover"`
- Add `HISTORY_FILE = HISTORY_DIR / "history.log"`
- In `_remove_selected()`, after successful removal (before `_load_packages`):
  - Open `HISTORY_FILE` in append mode
  - Write: `{timestamp} | REMOVED | {pkg_name} | {pkg_size}` per package

**Format:**
```
2026-06-04 03:15:22 | REMOVED | firefox | 152.3MB
2026-06-04 03:15:22 | REMOVED | thunderbird | 89.1MB
```

## Feature 6: Batch Chunking (gui.py)

Split large removal lists into groups of 50 to avoid ARG_MAX with `pkexec`.

**Changes in `gui.py` `_remove_selected()`:**
- Define `BATCH_SIZE = 50`
- Chunk `names` into batches: `[names[i:i + BATCH_SIZE] for i in range(0, len(names), BATCH_SIZE)]`
- Loop over batches:
  - Run `pkexec pacman -Rns --noconfirm` for each batch
  - If any batch fails, stop and show error (don't continue to next batch)
- Update progress label: "Removing batch N of M..."

---

## Files Touched

| File | Changes |
|---|---|
| `gui.py` | Select All/Deselect All buttons or header checkbox, history logging, batch chunking |

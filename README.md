# unused-pkg-remover

A PySide6 GUI tool to find and remove unused space on Arch Linux — orphan
packages, pacman cache, Flatpak runtimes, broken packages, AUR build deps,
Steam/Proton junk, and more.

## Features

### 9 Scan Modes

| Mode | What It Finds |
|------|--------------|
| **Orphans** | Packages no longer required by any installed package (`pacman -Qtdq`) |
| **Pacman Cache** | Cached package versions not currently installed |
| **All Pacman Cache** | **Every** `.pkg.tar.*` file in `/var/cache/pacman/pkg/` |
| **AUR Cache** | Source/build directories under `~/.cache/yay/` and `~/.cache/paru/` |
| **Flatpak Runtimes** | Unused Flatpak runtimes (`flatpak list --unused`) |
| **Broken Packages** | Packages with missing files (`pacman -Qk`) |
| **AUR Build Deps** | Orphaned AUR packages (no longer needed by any installed package) |
| **Orphaned Proton Prefixes** | Steam app compatdata directories whose game is no longer installed |
| **Obsolete Steam Runtimes** | Steam runtime/build directories not referenced by any installed game |
| **Stale Launcher Runners** | Runner directories from Lutris, Heroic, or Bottles |

Modes that require unavailable tools are hidden from the dropdown automatically.

### Removal

- All removals use **`pkexec`** for a GUI privilege elevation dialog
- Orphans removed with `pacman -Rns` (safe recursive removal)
- Cache files removed with `rm -f` under `pkexec`
- Flatpak runtimes removed with `flatpak uninstall -y`
- AUR build deps cleaned with `yay -Yc --noconfirm`
- AUR cache cleaned via `rm -rf` on source directories
- Steam/Proton/launcher directories cleaned via `rm -rf`
- Batch chunking (50 packages max) to avoid ARG_MAX
- Progress dialog with cancel support

### Safety

- Built-in safe list of ~100 critical system packages (never shown)
- Ignore files: `~/.unused-ignore`, `~/.config/unused-pkg-remover/ignore`, `./.unused-ignore`
- Add packages to ignore list directly from the GUI
- Dependency check via `pactree` (fallback `pacman -Qi`) before orphan removal
- Confirmation details dialog with package sizes, types, and total reclaimable
- Dry-run mode (`--dry-run`)
- Force mode (`--no-deps`) skips dependency checks

### Convenience

- Search bar to filter packages by name as you type
- Select-all row to toggle all visible checkboxes
- Sorted by installed size (largest first)
- Color-coded size column (red > 100 MB, orange > 10 MB, green otherwise)
- AUR/cache/flatpak/broken type badges with distinct colors
- Removal history log (`~/.local/share/unused-pkg-remover/history.log`)
- History viewer with reinstall capability
- Dark theme UI (Fusion + custom palette)
- Window geometry remembered via `QSettings`

## Requirements

- Python 3.11+
- PySide6 >= 6.5
- `pacman`, `expac`, `pkexec`
- Arch Linux (or derivative with compatible package tools)
- Optional: `flatpak`, `yay`/`paru`, `steam`, `lutris`, `heroic`, `bottles`

## Installation

```bash
pip install .
```

Run with:

```bash
unused-pkg-remover
```

Or directly:

```bash
python main.py
```

## CLI Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Show what would be removed without actually removing |
| `--no-deps` | Skip dependency checks and force removal of packages |

```bash
unused-pkg-remover --dry-run --no-deps
```

## Ignore List

Packages excluded from orphan results can be added to any of these files:

- `~/.unused-ignore`
- `~/.config/unused-pkg-remover/ignore`
- `./.unused-ignore` (project-local)

One package name per line. Lines starting with `#` are ignored.

```text
# manually installed AUR helper
paru
yay
# custom kernel modules
nvidia
```

Packages can also be added to `./.unused-ignore` directly from the GUI via the
**Add to Ignore** button.

## How It Works

### Orphan Detection

Orphans are detected via `pacman -Qtdq` — packages installed as dependencies
but no longer required by any explicitly installed package. Results are enriched
with installed size and description via `expac`.

A built-in safe list of ~100 critical system packages is always excluded.
Additional exclusions go in ignore files (see [Ignore List](#ignore-list)).

### Dependency Check

Before removal, the tool checks whether any installed packages depend on your
selection using `pactree -r -u`. If `pactree` is unavailable, it falls back to
parsing `pacman -Qi` output.

If dependents are found, a warning is shown in the confirmation dialog. This is
a **warning only** — it does not block removal.

### Removal Flow

1. **Normal removal** — `pkexec pacman -Rns --noconfirm`
2. **Dependency conflict** — A dialog appears with a **Force Remove (--nodeps)**
   button that re-runs with `--nodeps`
3. **Force mode** (`--no-deps` flag) — skips the dialog entirely

Non-pacman modes (cache, flatpak, Steam, etc.) use appropriate tools:
`pkexec rm`, `flatpak uninstall`, `yay -Yc`, or `rm -rf` on user-owned dirs.

## Project

```
unused-pkg-remover/
├── main.py                    # Entry point shim
├── pyproject.toml             # Package metadata & CLI entry point
├── unused_pkg_remover/
│   ├── __init__.py
│   ├── main.py                # Display check & GUI launcher
│   ├── gui.py                 # Qt6 window, table, theme, removal logic
│   ├── scanner.py             # All scanning functions (orphans, cache, flatpak, broken, Steam, …)
│   └── services.py            # Removal, logging, ignore operations
├── tests/
│   ├── test_scanner.py        # 40+ tests with mocked subprocess
│   ├── test_services.py       # Service layer tests
│   ├── test_main.py           # CLI argument tests
│   └── test_gui_utils.py      # Formatting/sorting utility tests
├── .github/workflows/ci.yml   # ruff lint/format + pytest (3.11/3.12/3.13)
└── README.md
```

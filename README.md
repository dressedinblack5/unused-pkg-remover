# unused-pkg-remover

<p align="center">
  <img src="assets/unused-pkg-remover.png">
</p>

PySide6 GUI for reclaiming disk space on Arch Linux — orphans, pacman cache,
Flatpak runtimes, broken packages, AUR build deps, Steam/Proton junk,
NPM cache/stale modules, and more.

## Features

- **12 scan modes**: Orphans, Pacman Cache, AUR Cache, Flatpak Runtimes,
  Broken Packages, Ollama Models, AUR Build Deps, Orphaned Proton Prefixes,
  Obsolete Steam Runtimes, Stale Launcher Runners, NPM Cache, Stale node_modules
- **Multi-Steam-library support**: Scans all Steam library folders via
  `libraryfolders.vdf` for Proton prefixes and runtimes, not just the default
- **Flatpak**: Uses `flatpak list --unused` (with fallback for older flatpak)
- **AUR Cache**: Handles both yay (`~/.cache/yay`) and paru (`~/.cache/paru/clone/`)
- **Launcher runners**: Scans Lutris, Heroic, Bottles — both native and Flatpak installs
- **Safe removal** via `pkexec`, batch-chunked (50 max), progress dialog with cancel
- **Safety nets**: built-in safe list (~100 critical packages), ignore files,
  dependency check via `pactree`, dry-run and force mode
- **Convenience**: search bar, select-all, color-coded sizes, type badges, dark
  theme, removal history with reinstall

Modes requiring unavailable tools are hidden automatically.

## Requirements

- Python 3.11+, PySide6 >= 6.5, Arch Linux (or derivative)
- `pacman`, `expac`, `pkexec`
- Optional: `flatpak`, `ollama`, `yay`/`paru`, `steam`, `lutris`, `heroic`, `bottles`, `npm`

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dressedinblack5/unused-pkg-remover/main/install.sh | sh
```

Requires Python 3.11+, PySide6, and Arch Linux (or derivative). PySide6 can be
installed via pacman for fastest setup:

```bash
sudo pacman -S pyside6
```

Run: `unused-pkg-remover`

## Usage

```bash
unused-pkg-remover              # normal mode
unused-pkg-remover --dry-run    # preview only
unused-pkg-remover --no-deps    # skip dependency checks
```

## Ignore List

Exclude packages from orphan results by adding them (one per line) to:

- `~/.unused-ignore`
- `~/.config/unused-pkg-remover/ignore`
- `./.unused-ignore` (project-local)

Can also be done from the GUI via the **Add to Ignore** button.

```text
# manually installed AUR helper
paru
yay
```

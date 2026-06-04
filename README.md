# unused-pkg-remover

Scan Arch Linux for orphaned packages and remove them via a GUI.

## Features

- Detects orphan packages (`pacman -Qtdq`)
- Sorted by installed size (largest first)
- AUR vs repo package markers
- Dark theme UI
- Built-in safe list excludes critical system packages
- `pkexec`-based removal with polkit authentication
- Ignore list via `~/.unused-ignore` or `./.unused-ignore`
- Window geometry remembered between sessions

## Requirements

- Python 3
- PySide6
- pacman, expac, pkexec

## Usage

```bash
python3 main.py
```

Select packages via checkboxes, then click **Remove Selected** or **Add to Ignore**.

## Ignore List

Create `~/.unused-ignore` or `./.unused-ignore` with one package per line:

```text
# packages to protect
my-custom-package
another-package
```

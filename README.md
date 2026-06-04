# unused-pkg-remover

Scan Arch Linux for orphaned packages and interactively remove them.

## Features

- Detects orphan packages (`pacman -Qtdq`)
- Sorts by installed size (largest first)
- Marks AUR vs repo packages
- Colorized output
- Ignore list support (`~/.unused-ignore` or `./.unused-ignore`)

## Usage

```bash
python3 main.py
```

Select packages by index (e.g., `0, 2, 5`) and confirm to uninstall.

## Ignore List

Create `~/.unused-ignore` or `./.unused-ignore` with one package per line:

```text
# packages to protect
grub
ntfs-3g
```

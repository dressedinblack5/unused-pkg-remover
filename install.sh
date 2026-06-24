#!/bin/sh
set -e

REPO="dressedinblack5/unused-pkg-remover"

echo "==> unused-pkg-remover installer"
echo ""

# Check Python
if ! python3 --version >/dev/null 2>&1; then
    echo "Error: Python 3.11+ is required"
    exit 1
fi

# Suggest PySide6 from system packages on Arch
if pacman -Q pyside6 >/dev/null 2>&1; then
    echo "[ok] PySide6 found (system package)"
else
    echo "[!] PySide6 not found via pacman."
    echo "    Install it from the system repo for fastest setup:"
    echo "    sudo pacman -S pyside6"
    echo ""
fi

# Check pip
if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "Error: pip is required"
    echo "Install: sudo pacman -S python-pip"
    exit 1
fi

echo "Installing unused-pkg-remover..."
python3 -m pip install "git+https://github.com/$REPO.git"

echo ""
echo "Done. Run: unused-pkg-remover"

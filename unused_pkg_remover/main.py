#!/usr/bin/env python3
import os
import sys

def main():
    display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if not display:
        print("No display available. Cannot launch GUI.")
        sys.exit(1)

    try:
        from unused_pkg_remover.gui import run_gui
        run_gui()
    except ImportError as e:
        print(f"Failed to import GUI module: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

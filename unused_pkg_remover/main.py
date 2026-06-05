#!/usr/bin/env python3
import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove orphaned Arch Linux packages")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without actually removing",
    )
    parser.add_argument(
        "--no-deps",
        action="store_true",
        help="Skip dependency checks and force removal of packages",
    )
    args = parser.parse_args()

    display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if not display:
        print("No display available. Cannot launch GUI.")
        sys.exit(1)

    try:
        from unused_pkg_remover.gui import run_gui

        run_gui(dry_run=args.dry_run, force_remove=args.no_deps)
    except ImportError as e:
        print(f"Failed to import GUI module: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

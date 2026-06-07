import os
import re
import shutil
import subprocess
from pathlib import Path

from .constants import _CACHE_EXTS, format_size


class RemovalError(Exception):
    """Raised when package removal via pacman fails."""


_data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
HISTORY_DIR = _data_home / "unused-pkg-remover"
HISTORY_FILE = HISTORY_DIR / "history.log"
BATCH_SIZE = 50


def remove_packages_batch(names: list[str], force: bool = False) -> None:
    base = ["pkexec", "pacman", "-Rns", "--nodeps"] if force else ["pkexec", "pacman", "-Rns"]
    try:
        subprocess.run(
            base + ["--noconfirm"] + names,
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "LANG": "C"},
        )
    except subprocess.CalledProcessError as e:
        raise RemovalError(e.stderr or str(e)) from e


def log_removal(packages: list[dict]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "a") as f:
        from datetime import datetime

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for pkg in packages:
            size_str = format_size(pkg["size"])
            f.write(f"{ts} | REMOVED | {pkg['name']} | {size_str}\n")


def add_to_ignore(ignore_file_path: Path, package_names: list[str]) -> None:
    with open(ignore_file_path, "a") as f:
        for name in package_names:
            f.write(f"{name}\n")


def remove_cache_packages(names: list[str]) -> None:
    cache_dir = Path("/var/cache/pacman/pkg")
    files = []
    for name in names:
        pattern = re.compile(rf"^{re.escape(name)}-\d")
        for f in cache_dir.iterdir():
            if pattern.match(f.name):
                files.append(str(f))
    if not files:
        return
    try:
        subprocess.run(
            ["pkexec", "rm", "-f"] + files,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RemovalError(e.stderr or str(e)) from e


def remove_flatpak_packages(names: list[str]) -> None:
    try:
        subprocess.run(
            ["flatpak", "uninstall", "-y"] + names,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RemovalError(e.stderr or str(e)) from e


def remove_aur_deps() -> None:
    if shutil.which("yay"):
        cmd = ["yay", "-Yc", "--noconfirm"]
    elif shutil.which("paru"):
        cmd = ["paru", "-c", "--noconfirm"]
    else:
        raise RemovalError("No AUR helper found (yay or paru)")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RemovalError(e.stderr or str(e)) from e


def remove_all_cache_packages(keys: list[str]) -> None:
    """Remove specific cache files by their filename stems (extension excluded)."""
    cache_dir = Path("/var/cache/pacman/pkg")
    files = []
    for key in keys:
        for ext in _CACHE_EXTS:
            p = cache_dir / f"{key}{ext}"
            if p.exists():
                files.append(str(p))
                break
    if not files:
        return
    try:
        subprocess.run(
            ["pkexec", "rm", "-f"] + files,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RemovalError(e.stderr or str(e)) from e


def remove_aur_cache_packages(names: list[str]) -> None:
    """Remove AUR build source directories from yay/paru cache."""
    cache_roots = [Path.home() / ".cache" / "yay", Path.home() / ".cache" / "paru"]
    errors = []
    for name in names:
        for root in cache_roots:
            target = root / name
            if target.exists():
                try:
                    shutil.rmtree(target)
                except OSError as e:
                    errors.append(str(e))
    if errors:
        raise RemovalError("; ".join(errors))


def remove_orphaned_proton_prefixes(names: list[str]) -> None:
    compatdata = Path.home() / ".steam" / "steam" / "steamapps" / "compatdata"
    errors = []
    for name in names:
        target = compatdata / name
        if target.exists():
            try:
                shutil.rmtree(target)
            except OSError as e:
                errors.append(str(e))
    if errors:
        raise RemovalError("; ".join(errors))


def remove_obsolete_steam_runtimes(names: list[str]) -> None:
    common_dir = Path.home() / ".steam" / "steam" / "steamapps" / "common"
    errors = []
    for name in names:
        target = common_dir / name
        if target.exists():
            try:
                shutil.rmtree(target)
            except OSError as e:
                errors.append(str(e))
    if errors:
        raise RemovalError("; ".join(errors))


def remove_stale_launcher_runners(names: list[str]) -> None:
    lutris_root = Path.home() / ".local" / "share" / "lutris" / "runners"
    heroic_wine = Path.home() / ".config" / "heroic" / "tools" / "runners" / "wine"
    heroic_proton = Path.home() / ".config" / "heroic" / "tools" / "runners" / "proton"
    bottles_root = Path.home() / ".local" / "share" / "bottles" / "runners"
    errors = []
    for name in names:
        if name.startswith("lutris:"):
            target = lutris_root / name[7:]
        elif name.startswith("heroic:wine/"):
            target = heroic_wine / name[12:]
        elif name.startswith("heroic:proton/"):
            target = heroic_proton / name[14:]
        elif name.startswith("bottles:"):
            target = bottles_root / name[8:]
        else:
            continue
        if target.exists():
            try:
                shutil.rmtree(target)
            except OSError as e:
                errors.append(str(e))
    if errors:
        raise RemovalError("; ".join(errors))

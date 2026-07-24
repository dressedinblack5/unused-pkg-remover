"""Service layer handling system commands and file operations for the remover."""

import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .constants import format_size
from .scanner import get_steam_library_paths

RemovalError = RuntimeError


_data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
HISTORY_DIR = _data_home / "unused-pkg-remover"
HISTORY_FILE = HISTORY_DIR / "history.log"
BATCH_SIZE = 50


def run_pkexec(
    cmd: list[str],
    *,
    cancel_check: Callable | None = None,
    timeout: float = 120,
) -> str:
    """Run a pkexec command with polling for cancellation and timeout.

    Returns stdout on success. Raises RemovalError on failure.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "LANG": "C"},
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel_check and cancel_check():
            proc.kill()
            proc.wait()
            raise RemovalError("Cancelled") from None
        try:
            stdout, stderr = proc.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            continue
        if proc.returncode != 0:
            raise RemovalError(stderr or str(proc.returncode)) from None
        return stdout

    proc.kill()
    proc.wait()
    raise RemovalError("Authentication timed out or no polkit agent available") from None


def remove_packages_batch(
    names: list[str], force: bool = False, cancel_check: Callable | None = None
) -> None:
    base = ["pkexec", "pacman", "-Rns", "--nodeps"] if force else ["pkexec", "pacman", "-Rns"]
    run_pkexec(base + ["--noconfirm"] + names, cancel_check=cancel_check)


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


def remove_cache_packages(names: list[str], *, cancel_check: Callable | None = None) -> None:
    cache_dir = Path("/var/cache/pacman/pkg")
    files = []
    for name in names:
        pattern = re.compile(rf"^{re.escape(name)}-\d")
        for f in cache_dir.iterdir():
            if pattern.match(f.name):
                files.append(str(f))
    if not files:
        return
    run_pkexec(["pkexec", "rm", "-f"] + files, cancel_check=cancel_check)


def remove_flatpak_packages(names: list[str], *, cancel_check: Callable | None = None) -> None:
    if cancel_check and cancel_check():
        raise RemovalError("Cancelled")
    try:
        subprocess.run(
            ["flatpak", "uninstall", "-y"] + names,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RemovalError(e.stderr or str(e)) from e


def remove_aur_deps(*, cancel_check: Callable | None = None) -> None:
    if cancel_check and cancel_check():
        raise RemovalError("Cancelled")
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


def remove_aur_cache_packages(names: list[str]) -> None:
    """Remove AUR build source directories from yay/paru cache."""
    cache_roots = [Path.home() / ".cache" / "yay"]
    paru_cache = Path.home() / ".cache" / "paru"
    if paru_cache.exists():
        paru_root = paru_cache / "clone"
        if not paru_root.exists():
            paru_root = paru_cache
        cache_roots.append(paru_root)
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
    library_paths = get_steam_library_paths()
    errors = []
    for name in names:
        for lib_path in library_paths:
            target = lib_path / "steamapps" / "compatdata" / name
            if target.exists():
                try:
                    shutil.rmtree(target)
                except OSError as e:
                    errors.append(str(e))
                break
    if errors:
        raise RemovalError("; ".join(errors))


def remove_obsolete_steam_runtimes(names: list[str]) -> None:
    library_paths = get_steam_library_paths()
    errors = []
    for name in names:
        for lib_path in library_paths:
            target = lib_path / "steamapps" / "common" / name
            if target.exists():
                try:
                    shutil.rmtree(target)
                except OSError as e:
                    errors.append(str(e))
                break
    if errors:
        raise RemovalError("; ".join(errors))


def remove_ollama_models(names: list[str], *, cancel_check: Callable | None = None) -> None:
    if cancel_check and cancel_check():
        raise RemovalError("Cancelled")
    try:
        subprocess.run(
            ["ollama", "rm"] + names,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RemovalError(e.stderr or str(e)) from e


def remove_stale_launcher_runners(names: list[str]) -> None:
    _home = Path.home()
    lutris_root = _home / ".local" / "share" / "lutris" / "runners"
    heroic_wine = _home / ".config" / "heroic" / "tools" / "runners" / "wine"
    heroic_proton = _home / ".config" / "heroic" / "tools" / "runners" / "proton"
    bottles_root = _home / ".local" / "share" / "bottles" / "runners"
    prefix_roots: dict[str, Path] = {
        "lutris:": lutris_root,
        "heroic:wine/": heroic_wine,
        "heroic:proton/": heroic_proton,
        "bottles:": bottles_root,
    }

    # Flatpak installs
    var = _home / ".var" / "app"
    flatpak_lutris = var / "net.lutris.Lutris" / "data" / "lutris" / "runners"
    if flatpak_lutris.exists():
        prefix_roots["lutris:"] = flatpak_lutris  # overrides native if Flatpak exists
    flatpak_bottles = var / "com.usebottles.bottles" / "data" / "bottles" / "runners"
    if flatpak_bottles.exists():
        prefix_roots["bottles:"] = flatpak_bottles
    heroic_base = var / "com.heroicgameslauncher.hgl" / "config" / "heroic" / "tools" / "runners"
    flatpak_heroic_wine = heroic_base / "wine"
    flatpak_heroic_proton = heroic_base / "proton"
    if flatpak_heroic_wine.exists():
        prefix_roots["heroic:wine/"] = flatpak_heroic_wine
    if flatpak_heroic_proton.exists():
        prefix_roots["heroic:proton/"] = flatpak_heroic_proton
    errors = []
    for name in names:
        matched = None
        for prefix, root in prefix_roots.items():
            if name.startswith(prefix):
                target = root / name[len(prefix) :]
                matched = prefix
                break
        if matched is None:
            continue
        prefix_root = str(prefix_roots[matched].resolve())
        if target.exists():
            resolved = target.resolve()
            if not str(resolved).startswith(prefix_root):
                errors.append(f"Path traversal blocked: {target}")
                continue
            try:
                shutil.rmtree(resolved)
            except OSError as e:
                errors.append(str(e))
    if errors:
        raise RemovalError("; ".join(errors))


def remove_npm_cache(*, cancel_check: Callable | None = None) -> None:
    """Clean the entire npm cache."""
    if cancel_check and cancel_check():
        raise RemovalError("Cancelled")
    try:
        subprocess.run(
            ["npm", "cache", "clean", "--force"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RemovalError(e.stderr or str(e)) from e


def remove_stale_node_modules(names: list[str], *, cancel_check: Callable | None = None) -> None:
    """Remove orphaned node_modules directories from deleted projects."""
    scan_dirs = [
        Path.home() / "Projects",
        Path.home() / "dev",
        Path.home() / "src",
        Path.home() / "workspace",
        Path.home() / "code",
    ]
    errors = []
    for name in names:
        found = False
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            target = scan_dir / name / "node_modules"
            if target.exists():
                try:
                    if cancel_check and cancel_check():
                        raise RemovalError("Cancelled")
                    shutil.rmtree(target)
                except OSError as e:
                    errors.append(str(e))
                found = True
                break
        if not found:
            errors.append(f"node_modules not found for: {name}")
    if errors:
        raise RemovalError("; ".join(errors))

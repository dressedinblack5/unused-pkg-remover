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

CancelCheck = Callable[[], bool]


def _validate_path_within_root(target: Path, allowed_root: Path) -> bool:
    """Validate that target path is within allowed_root to prevent path traversal."""
    try:
        resolved_target = target.resolve()
        resolved_root = allowed_root.resolve()
        try:
            return resolved_target.is_relative_to(resolved_root)
        except AttributeError:
            try:
                resolved_target.relative_to(resolved_root)
                return True
            except ValueError:
                return False
    except (OSError, RuntimeError, ValueError):
        return False


def _sanitize_package_name(name: str, *, allow_slash: bool = False) -> str:
    """Sanitize package name to prevent injection - allow only safe chars.

    Rejects leading '-' (option injection). '/' only when allow_slash=True
    (e.g. ollama namespaces); filesystem entries must use
    _sanitize_path_component instead.
    """
    import re

    pattern = (
        r"[A-Za-z0-9._@+:][A-Za-z0-9._@+:\-/]*"
        if allow_slash
        else (r"[A-Za-z0-9._@+:][A-Za-z0-9._@+:\-]*")
    )
    if not name or not re.fullmatch(pattern, name):
        raise RemovalError(f"Invalid package name: {name}")
    if ".." in name:
        raise RemovalError(f"Invalid package name: {name}")
    return name


def _sanitize_path_component(name: str) -> str:
    """Validate a single filesystem path component (no separators, no traversal)."""
    if not name or name in (".", ".."):
        raise RemovalError(f"Invalid path component: {name!r}")
    if "/" in name or "\\" in name or "\x00" in name:
        raise RemovalError(f"Invalid path component: {name!r}")
    if name != name.strip() or ".." in name.split():
        raise RemovalError(f"Invalid path component: {name!r}")
    return name


_data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
HISTORY_DIR = _data_home / "unused-pkg-remover"
HISTORY_FILE = HISTORY_DIR / "history.log"
BATCH_SIZE = 50


def run_pkexec(
    cmd: list[str],
    *,
    cancel_check: CancelCheck | None = None,
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
    names: list[str], force: bool = False, cancel_check: CancelCheck | None = None
) -> None:
    for name in names:
        _sanitize_package_name(name)
    base = ["pkexec", "pacman", "-Rns", "--nodeps"] if force else ["pkexec", "pacman", "-Rns"]
    run_pkexec(base + ["--noconfirm"] + names, cancel_check=cancel_check)


def log_removal(packages: list[dict[str, str | int | bool]]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "a") as f:
        from datetime import datetime

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for pkg in packages:
            size_str = format_size(pkg["size"])
            f.write(f"{ts} | REMOVED | {pkg['name']} | {size_str}\n")


def add_to_ignore(ignore_file_path: Path, package_names: list[str]) -> None:
    import contextlib

    with contextlib.suppress(OSError):
        ignore_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ignore_file_path, "a") as f:
        for name in package_names:
            f.write(f"{name}\n")


def remove_cache_packages(names: list[str], *, cancel_check: CancelCheck | None = None) -> None:
    from .constants import _CACHE_EXTS

    for name in names:
        _sanitize_package_name(name)
    cache_dir = Path("/var/cache/pacman/pkg")
    files = []
    for name in names:
        pattern = re.compile(rf"^{re.escape(name)}-\d", re.IGNORECASE)
        for f in cache_dir.iterdir():
            if not any(f.name.endswith(ext) for ext in _CACHE_EXTS):
                continue
            if pattern.match(f.name):
                target = cache_dir / f.name
                if _validate_path_within_root(target, cache_dir):
                    files.append(str(target))
    if not files:
        return
    run_pkexec(["pkexec", "rm", "-f"] + files, cancel_check=cancel_check)


def remove_flatpak_packages(names: list[str], *, cancel_check: CancelCheck | None = None) -> None:
    for name in names:
        _sanitize_package_name(name, allow_slash=True)
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


def remove_aur_deps(*, cancel_check: CancelCheck | None = None) -> None:
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


def remove_aur_cache_packages(names: list[str], *, cancel_check: CancelCheck | None = None) -> None:
    """Remove AUR build source directories from yay/paru cache."""
    for name in names:
        _sanitize_path_component(name)
    cache_roots = [Path.home() / ".cache" / "yay"]
    paru_cache = Path.home() / ".cache" / "paru"
    if paru_cache.exists():
        paru_root = paru_cache / "clone"
        if not paru_root.exists():
            paru_root = paru_cache
        cache_roots.append(paru_root)
    errors = []
    for name in names:
        if cancel_check and cancel_check():
            raise RemovalError("Cancelled")
        for root in cache_roots:
            target = root / name
            if target.exists():
                if _validate_path_within_root(target, root):
                    try:
                        shutil.rmtree(target)
                    except OSError as e:
                        errors.append(str(e))
                else:
                    errors.append(f"Path traversal blocked: {target}")
    if errors:
        raise RemovalError("; ".join(errors))


def remove_orphaned_proton_prefixes(
    names: list[str], *, cancel_check: CancelCheck | None = None
) -> None:
    library_paths = get_steam_library_paths()
    errors = []
    for name in names:
        if not name.isdigit():
            raise RemovalError(f"Invalid Proton prefix id: {name}")
        if cancel_check and cancel_check():
            raise RemovalError("Cancelled")
        for lib_path in library_paths:
            target = lib_path / "steamapps" / "compatdata" / name
            if target.exists():
                if _validate_path_within_root(target, lib_path):
                    try:
                        shutil.rmtree(target)
                    except OSError as e:
                        errors.append(str(e))
                else:
                    errors.append(f"Path traversal blocked: {target}")
                break
    if errors:
        raise RemovalError("; ".join(errors))


def remove_obsolete_steam_runtimes(
    names: list[str], *, cancel_check: CancelCheck | None = None
) -> None:
    library_paths = get_steam_library_paths()
    errors = []
    for name in names:
        _sanitize_path_component(name)
        if cancel_check and cancel_check():
            raise RemovalError("Cancelled")
        for lib_path in library_paths:
            target = lib_path / "steamapps" / "common" / name
            if target.exists():
                if _validate_path_within_root(target, lib_path):
                    try:
                        shutil.rmtree(target)
                    except OSError as e:
                        errors.append(str(e))
                else:
                    errors.append(f"Path traversal blocked: {target}")
                break
    if errors:
        raise RemovalError("; ".join(errors))


def remove_ollama_models(names: list[str], *, cancel_check: CancelCheck | None = None) -> None:
    for name in names:
        _sanitize_package_name(name, allow_slash=True)
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


def remove_stale_launcher_runners(
    names: list[str], *, cancel_check: CancelCheck | None = None
) -> None:
    _home = Path.home()
    lutris_roots = [_home / ".local" / "share" / "lutris" / "runners"]
    heroic_wine_roots = [_home / ".config" / "heroic" / "tools" / "runners" / "wine"]
    heroic_proton_roots = [_home / ".config" / "heroic" / "tools" / "runners" / "proton"]
    bottles_roots = [_home / ".local" / "share" / "bottles" / "runners"]
    prefix_roots: dict[str, list[Path]] = {
        "lutris:": lutris_roots,
        "heroic:wine/": heroic_wine_roots,
        "heroic:proton/": heroic_proton_roots,
        "bottles:": bottles_roots,
    }

    # Flatpak installs (kept alongside native so both stay removable)
    var = _home / ".var" / "app"
    flatpak_lutris = var / "net.lutris.Lutris" / "data" / "lutris" / "runners"
    if flatpak_lutris.exists():
        prefix_roots["lutris:"].append(flatpak_lutris)
    flatpak_bottles = var / "com.usebottles.bottles" / "data" / "bottles" / "runners"
    if flatpak_bottles.exists():
        prefix_roots["bottles:"].append(flatpak_bottles)
    heroic_base = var / "com.heroicgameslauncher.hgl" / "config" / "heroic" / "tools" / "runners"
    flatpak_heroic_wine = heroic_base / "wine"
    flatpak_heroic_proton = heroic_base / "proton"
    if flatpak_heroic_wine.exists():
        prefix_roots["heroic:wine/"].append(flatpak_heroic_wine)
    if flatpak_heroic_proton.exists():
        prefix_roots["heroic:proton/"].append(flatpak_heroic_proton)
    errors = []
    for name in names:
        if cancel_check and cancel_check():
            raise RemovalError("Cancelled")
        matched_roots = None
        remainder = ""
        for prefix, roots in prefix_roots.items():
            if name.startswith(prefix):
                remainder = name[len(prefix) :]
                matched_roots = roots
                break
        if matched_roots is None:
            continue
        _sanitize_path_component(remainder)
        for root in matched_roots:
            target = root / remainder
            if target.exists():
                if _validate_path_within_root(target, root):
                    try:
                        shutil.rmtree(target)
                    except OSError as e:
                        errors.append(str(e))
                else:
                    errors.append(f"Path traversal blocked: {target}")
                break
    if errors:
        raise RemovalError("; ".join(errors))


def remove_npm_cache(*, cancel_check: CancelCheck | None = None) -> None:
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


def remove_stale_node_modules(names: list[str], *, cancel_check: CancelCheck | None = None) -> None:
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
        _sanitize_path_component(name)
        found = False
        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            target = scan_dir / name / "node_modules"
            if target.exists():
                if _validate_path_within_root(target, scan_dir):
                    try:
                        if cancel_check and cancel_check():
                            raise RemovalError("Cancelled")
                        shutil.rmtree(target)
                    except OSError as e:
                        errors.append(str(e))
                else:
                    errors.append(f"Path traversal blocked: {target}")
                found = True
                break
        if not found:
            errors.append(f"node_modules not found for: {name}")
    if errors:
        raise RemovalError("; ".join(errors))

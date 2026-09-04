"""GUI constants for scan modes, removal labels, and UI settings."""

import shutil
from pathlib import Path

from ..scanner import (
    ScanFunc,
    get_aur_build_deps,
    get_aur_cache_packages,
    get_broken_packages,
    get_cache_packages,
    get_npm_cache_packages,
    get_obsolete_steam_runtimes,
    get_ollama_models,
    get_orphaned_proton_prefixes,
    get_stale_launcher_runners,
    get_stale_node_modules,
    get_unused_flatpaks,
    get_unused_packages,
)

_SCAN_FUNCTIONS: dict[str, ScanFunc] = {
    "orphans": get_unused_packages,
    "cache": lambda: (get_cache_packages(), 0),
    "flatpak": lambda: (get_unused_flatpaks(), 0),
    "broken": lambda: (get_broken_packages(), 0),
    "aur-dep": lambda: (get_aur_build_deps(), 0),
    "aur-cache": lambda: (get_aur_cache_packages(), 0),
    "proton-prefix": lambda: (get_orphaned_proton_prefixes(), 0),
    "steam-runtime": lambda: (get_obsolete_steam_runtimes(), 0),
    "ollama": lambda: (get_ollama_models(), 0),
    "launcher-runner": lambda: (get_stale_launcher_runners(), 0),
    "npm-cache": lambda: (get_npm_cache_packages(), 0),
    "npm-stale": lambda: (get_stale_node_modules(), 0),
}

_REMOVAL_LABELS: dict[str, str] = {
    "cache": "Removing cached packages...",
    "flatpak": "Removing Flatpak runtimes...",
    "aur-dep": "Removing AUR build deps...",
    "aur-cache": "Removing AUR build sources...",
    "proton-prefix": "Removing Proton prefixes...",
    "steam-runtime": "Removing Steam runtimes...",
    "ollama": "Removing Ollama models...",
    "launcher-runner": "Removing launcher runners...",
    "npm-cache": "Removing npm cache...",
    "npm-stale": "Removing stale NPM modules...",
}

_AVAILABLE_MODES_CACHE: list[tuple[str, str]] | None = None


def _has_flatpak() -> bool:
    return shutil.which("flatpak") is not None


def _has_ollama() -> bool:
    return shutil.which("ollama") is not None


def _has_aur_helper() -> bool:
    return shutil.which("yay") is not None or shutil.which("paru") is not None


def _has_npm() -> bool:
    return shutil.which("npm") is not None


def _has_project_dirs() -> bool:
    home = Path.home()
    return any(home.joinpath(p).exists() for p in ["Projects", "dev", "src", "workspace", "code"])


def _has_steam() -> bool:
    steam_dir = Path.home() / ".steam" / "steam"
    return steam_dir.exists()


def _has_steam_compatdata() -> bool:
    steam_dir = Path.home() / ".steam" / "steam"
    vdf_path = steam_dir / "steamapps" / "libraryfolders.vdf"
    compatdata = steam_dir.joinpath("steamapps/compatdata")
    return steam_dir.exists() and (compatdata.exists() or vdf_path.exists())


def _has_steam_common() -> bool:
    steam_dir = Path.home() / ".steam" / "steam"
    vdf_path = steam_dir / "steamapps" / "libraryfolders.vdf"
    common = steam_dir.joinpath("steamapps/common")
    return steam_dir.exists() and (common.exists() or vdf_path.exists())


def _has_launcher_runners() -> bool:
    home = Path.home()
    return any(
        home.joinpath(p).exists()
        for p in [
            ".local/share/lutris/runners",
            ".config/heroic",
            ".local/share/bottles/runners",
            ".var/app/net.lutris.Lutris/data/lutris/runners",
            ".var/app/com.heroicgameslauncher.hgl/config/heroic",
            ".var/app/com.usebottles.bottles/data/bottles/runners",
        ]
    )


def get_available_modes() -> list[tuple[str, str]]:
    """Get available scan modes, computing them lazily on first call."""
    global _AVAILABLE_MODES_CACHE
    if _AVAILABLE_MODES_CACHE is not None:
        return _AVAILABLE_MODES_CACHE

    modes: list[tuple[str, str]] = [
        ("orphans", "Orphans"),
        ("cache", "Pacman Cache"),
    ]
    if _has_flatpak():
        modes.append(("flatpak", "Flatpak Runtimes"))
    modes.append(("broken", "Broken Packages"))
    if _has_ollama():
        modes.append(("ollama", "Ollama Models"))
    if _has_aur_helper():
        modes.append(("aur-dep", "AUR Build Deps"))
        modes.append(("aur-cache", "AUR Build Cache"))
    if _has_npm():
        modes.append(("npm-cache", "NPM Cache"))
        if _has_project_dirs():
            modes.append(("npm-stale", "NPM Stale Modules"))
    if _has_steam_compatdata():
        modes.append(("proton-prefix", "Proton Prefixes"))
    if _has_steam_common():
        modes.append(("steam-runtime", "Steam Runtimes"))
    if _has_launcher_runners():
        modes.append(("launcher-runner", "Launcher Runners"))

    _AVAILABLE_MODES_CACHE = modes
    return modes


def get_ignore_file() -> Path:
    return Path.home() / ".unused-ignore"


def reset_available_modes_cache() -> None:
    global _AVAILABLE_MODES_CACHE
    _AVAILABLE_MODES_CACHE = None


COL_SELECT = 0
COL_NAME = 1
COL_SIZE = 2
COL_TYPE = 3
COL_DESC = 4

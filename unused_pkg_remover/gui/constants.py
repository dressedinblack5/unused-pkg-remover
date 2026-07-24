"""GUI constants for scan modes, removal labels, and UI settings."""

import shutil
from pathlib import Path

from ..scanner import (
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

_SCAN_FUNCTIONS = {
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

_REMOVAL_LABELS = {
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

_AVAILABLE_MODES: list[tuple[str, str]] = [
    ("orphans", "Orphans"),
    ("cache", "Pacman Cache"),
]
if shutil.which("flatpak"):
    _AVAILABLE_MODES.append(("flatpak", "Flatpak Runtimes"))
_AVAILABLE_MODES.append(("broken", "Broken Packages"))
if shutil.which("ollama"):
    _AVAILABLE_MODES.append(("ollama", "Ollama Models"))
has_aur_helper = shutil.which("yay") or shutil.which("paru")
if has_aur_helper:
    _AVAILABLE_MODES.append(("aur-dep", "AUR Build Deps"))
    _AVAILABLE_MODES.append(("aur-cache", "AUR Build Cache"))
_home = Path.home()
if shutil.which("npm"):
    _AVAILABLE_MODES.append(("npm-cache", "NPM Cache"))
    if any(
        _home.joinpath(p).exists() for p in ["Projects", "dev", "src", "workspace", "code"]
    ):
        _AVAILABLE_MODES.append(("npm-stale", "NPM Stale Modules"))

_steam_dir = _home / ".steam" / "steam"
_vdf_path = _steam_dir / "steamapps" / "libraryfolders.vdf"
_has_steam = _steam_dir.exists()
if _has_steam and (_steam_dir.joinpath("steamapps/compatdata").exists() or _vdf_path.exists()):
    _AVAILABLE_MODES.append(("proton-prefix", "Proton Prefixes"))
if _has_steam and (_steam_dir.joinpath("steamapps/common").exists() or _vdf_path.exists()):
    _AVAILABLE_MODES.append(("steam-runtime", "Steam Runtimes"))
if any(
    _home.joinpath(p).exists()
    for p in [
        ".local/share/lutris/runners",
        ".config/heroic",
        ".local/share/bottles/runners",
        ".var/app/net.lutris.Lutris/data/lutris/runners",
        ".var/app/com.heroicgameslauncher.hgl/config/heroic",
        ".var/app/com.usebottles.bottles/data/bottles/runners",
    ]
):
    _AVAILABLE_MODES.append(("launcher-runner", "Launcher Runners"))

def get_ignore_file() -> Path:
    return Path.cwd() / ".unused-ignore"


COL_SELECT = 0
COL_NAME = 1
COL_SIZE = 2
COL_TYPE = 3
COL_DESC = 4

_PROGRESS_STYLE = """
    QProgressDialog {
        background-color: #1e1e1e;
        color: #e0e0e0;
    }
    QProgressBar {
        border: 1px solid #3c3c3c;
        border-radius: 4px;
        background-color: #252526;
        text-align: center;
    }
    QProgressBar::chunk {
        background-color: #58a6ff;
        border-radius: 3px;
    }
"""

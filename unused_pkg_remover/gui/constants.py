import shutil
from pathlib import Path

from ..scanner import (
    get_all_cache_packages,
    get_aur_build_deps,
    get_aur_cache_packages,
    get_broken_packages,
    get_cache_packages,
    get_obsolete_steam_runtimes,
    get_ollama_models,
    get_orphaned_proton_prefixes,
    get_stale_launcher_runners,
    get_unused_flatpaks,
    get_unused_packages,
)
from ..services import (
    remove_all_cache_packages,
    remove_aur_cache_packages,
    remove_aur_deps,
    remove_cache_packages,
    remove_flatpak_packages,
    remove_obsolete_steam_runtimes,
    remove_ollama_models,
    remove_orphaned_proton_prefixes,
    remove_stale_launcher_runners,
)

_SCAN_FUNCTIONS = {
    "orphans": get_unused_packages,
    "cache": lambda: (get_cache_packages(), 0),
    "all-cache": lambda: (get_all_cache_packages(), 0),
    "flatpak": lambda: (get_unused_flatpaks(), 0),
    "broken": lambda: (get_broken_packages(), 0),
    "aur-dep": lambda: (get_aur_build_deps(), 0),
    "aur-cache": lambda: (get_aur_cache_packages(), 0),
    "proton-prefix": lambda: (get_orphaned_proton_prefixes(), 0),
    "steam-runtime": lambda: (get_obsolete_steam_runtimes(), 0),
    "ollama": lambda: (get_ollama_models(), 0),
    "launcher-runner": lambda: (get_stale_launcher_runners(), 0),
}

_REMOVAL_ACTIONS = {
    "cache": (
        "Removing cached packages...",
        lambda w: remove_cache_packages(w.names, cancel_check=lambda: w._cancelled),
    ),
    "all-cache": (
        "Removing cached package files...",
        lambda w: remove_all_cache_packages(w.names, cancel_check=lambda: w._cancelled),
    ),
    "flatpak": ("Removing Flatpak runtimes...", lambda w: remove_flatpak_packages(w.names)),
    "aur-dep": ("Cleaning AUR build deps...", lambda _: remove_aur_deps()),
    "aur-cache": ("Removing AUR build sources...", lambda w: remove_aur_cache_packages(w.names)),
    "proton-prefix": (
        "Removing Proton prefixes...",
        lambda w: remove_orphaned_proton_prefixes(w.names),
    ),
    "steam-runtime": (
        "Removing Steam runtimes...",
        lambda w: remove_obsolete_steam_runtimes(w.names),
    ),
    "ollama": (
        "Removing Ollama models...",
        lambda w: remove_ollama_models(w.names),
    ),
    "launcher-runner": (
        "Removing launcher runners...",
        lambda w: remove_stale_launcher_runners(w.names),
    ),
}

_AVAILABLE_MODES: list[tuple[str, str]] = [
    ("orphans", "Orphans"),
    ("cache", "Pacman Cache"),
    ("all-cache", "All Pacman Cache"),
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
if _home.joinpath(".steam/steam/steamapps/compatdata").exists():
    _AVAILABLE_MODES.append(("proton-prefix", "Proton Prefixes"))
if _home.joinpath(".steam/steam/steamapps/common").exists():
    _AVAILABLE_MODES.append(("steam-runtime", "Steam Runtimes"))
if any(
    _home.joinpath(p).exists()
    for p in [".local/share/lutris/runners", ".config/heroic", ".local/share/bottles/runners"]
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

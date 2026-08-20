"""Scanning utilities for detecting unused packages, caches, and other resources."""

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .constants import _CACHE_ARCHES, _CACHE_EXTS

# Type aliases
PackageDict = dict[str, str | int | bool]
ScanFunc = Callable[[], tuple[list[PackageDict], int]]


def _make_package(
    name: str,
    size: int,
    desc: str,
    type_tag: str,
    **extra: str | int | bool,
) -> PackageDict:
    """Create a standardized package dictionary."""
    pkg: PackageDict = {"name": name, "size": size, "desc": desc, "type_tag": type_tag}
    pkg.update(extra)
    return pkg


def _sort_by_size_desc(packages: list[PackageDict]) -> list[PackageDict]:
    """Sort packages by size descending."""
    packages.sort(key=lambda x: x["size"], reverse=True)
    return packages


def _deduplicate_by_name(packages: list[PackageDict], key: str = "name") -> list[PackageDict]:
    """Deduplicate packages by name, keeping first occurrence."""
    seen: set[str] = set()
    result: list[PackageDict] = []
    for pkg in packages:
        name = pkg[key]
        if name not in seen:
            seen.add(name)
            result.append(pkg)
    return result


def get_ignored_packages() -> set[str]:
    ignored: set[str] = set()
    paths = []
    if "UNUSED_IGNORE" in os.environ:
        paths.append(Path(os.environ["UNUSED_IGNORE"]))
    else:
        paths = [
            Path.home() / ".unused-ignore",
            Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
            / "unused-pkg-remover"
            / "ignore",
            Path.cwd() / ".unused-ignore",
        ]
    for p in paths:
        if p.exists():
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ignored.add(line.lower())
    return ignored


def get_aur_packages() -> set[str]:
    result = subprocess.run(["pacman", "-Qqm"], capture_output=True, text=True)
    if result.returncode != 0:
        return set()
    return {pkg.lower() for pkg in result.stdout.splitlines()}


def get_explicitly_installed_packages() -> set[str]:
    result = subprocess.run(["pacman", "-Qqe"], capture_output=True, text=True)
    if result.returncode != 0:
        return set()
    return {pkg.lower() for pkg in result.stdout.splitlines()}


def get_dependents(pkg_name: str) -> list[str]:
    deps = []
    if shutil.which("pactree"):
        # Try raw output first; fall back to stripping tree chars
        result = subprocess.run(["pactree", "-r", "-u", pkg_name], capture_output=True, text=True)
        if result.returncode != 0:
            result = subprocess.run(["pactree", "-r", pkg_name], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = re.sub(r"^[├└─│\s]+", "", line).strip()
                if line and line != pkg_name:
                    deps.append(line)
    else:
        result = subprocess.run(
            ["pacman", "-Qi", pkg_name],
            capture_output=True,
            text=True,
            env={**os.environ, "LANG": "C"},
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                ls = line.strip()
                if ls.startswith("Required By") or ls.startswith("Optional For"):
                    val = ls.split(":", 1)[-1].strip()
                    if val and val != "None":
                        deps.extend(d for d in val.split() if d)
                elif ls.startswith("Optional Deps"):
                    break
    return deps


def _get_orphan_names() -> list[str]:
    for cmd in [["yay", "-Qtdq"], ["paru", "-Qtdq"], ["pacman", "-Qtdq"]]:
        if shutil.which(cmd[0]):
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.splitlines()
    return []


def _query_expac(package_names: list[str]) -> list[PackageDict]:
    cmd = ["expac", "-Q", "%n|%l|%d|%m"] + package_names
    result = subprocess.run(cmd, capture_output=True, text=True)
    packages: list[PackageDict] = []
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 4:
            name, date, desc, size_str = parts
            try:
                size = int(size_str.strip())
            except ValueError:
                size = 0
            packages.append(
                _make_package(name=name, size=size, desc=desc, type_tag="repo", date=date)
            )
    return _sort_by_size_desc(packages)


def _get_base_packages() -> set[str]:
    """Packages in base/base-devel groups — never remove these."""
    try:
        result = subprocess.run(
            ["pacman", "-Qq", "--groups", "base", "base-devel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return set(result.stdout.splitlines())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return set()


def get_unused_packages() -> tuple[list[PackageDict], int]:
    if not shutil.which("expac"):
        raise RuntimeError("expac not found. Install it: sudo pacman -S expac")

    orphans = _get_orphan_names()
    if not orphans:
        return [], 0

    ignored = get_ignored_packages() | get_explicitly_installed_packages() | _get_base_packages()
    aur_pkgs = get_aur_packages()

    unused: list[PackageDict] = []
    filtered_count = 0
    for pkg in _query_expac(orphans):
        if pkg["name"].lower() in ignored:
            filtered_count += 1
            continue
        pkg = dict(pkg)
        pkg["is_aur"] = pkg["name"].lower() in aur_pkgs
        unused.append(pkg)

    return unused, filtered_count


def _get_installed_packages() -> dict[str, str]:
    result = subprocess.run(["pacman", "-Q"], capture_output=True, text=True)
    if result.returncode != 0:
        return {}
    installed = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            installed[parts[0].lower()] = parts[1]
    return installed


def _extract_cache_pkg_name(filename: str) -> str:
    stem = filename
    for ext in _CACHE_EXTS:
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break
    for arch in _CACHE_ARCHES:
        if stem.endswith(arch):
            stem = stem[: -len(arch)]
            break
    for _ in range(2):
        idx = stem.rfind("-")
        if idx > 0 and re.fullmatch(r"[\d.:]+", stem[idx + 1 :]):
            stem = stem[:idx]
        else:
            break
    return stem.lower()


def _iter_cache_entries() -> list[dict]:
    """Return {stem, extracted, size, installed} for each pacman cache file."""
    cache_dir = Path("/var/cache/pacman/pkg")
    if not cache_dir.exists():
        return []
    installed = _get_installed_packages()
    entries = []
    for f in cache_dir.iterdir():
        if not f.is_file() or not any(f.name.endswith(ext) for ext in _CACHE_EXTS):
            continue
        extracted = _extract_cache_pkg_name(f.name)
        stem = f.name
        for ext in _CACHE_EXTS:
            if stem.endswith(ext):
                stem = stem[: -len(ext)]
                break
        entries.append(
            {
                "stem": stem,
                "extracted": extracted,
                "size": f.stat().st_size,
                "installed": extracted in installed,
            }
        )
    return entries


def get_cache_packages() -> list[PackageDict]:
    """All cached packages grouped by package name, including installed packages."""
    by_name: dict[str, list[dict]] = {}
    for e in _iter_cache_entries():
        by_name.setdefault(e["extracted"], []).append(e)
    packages = [
        _make_package(
            name=name,
            size=sum(e["size"] for e in entries),
            desc=(
                f"{len(entries)} cached version(s)"
                + (", not installed" if not entries[0]["installed"] else "")
            ),
            type_tag="cache",
        )
        for name, entries in by_name.items()
    ]
    return _sort_by_size_desc(packages)


def _parse_human_size(s: str) -> int:
    s = s.strip().lower()
    for unit, mul in [("kb", 1024), ("mb", 1024**2), ("gb", 1024**3), ("tb", 1024**4)]:
        if s.endswith(unit):
            try:
                return int(float(s[: -len(unit)].strip().rstrip(".")) * mul)
            except ValueError:
                return 0
    try:
        return int(s)
    except ValueError:
        return 0


def get_unused_flatpaks() -> list[PackageDict]:
    if not shutil.which("flatpak"):
        return []
    env = {**os.environ, "LANG": "C"}

    names: list[str] = []
    # flatpak list --unused added in flatpak 1.14.
    # Try it first; if flatpak doesn't recognise --unused, fall back to
    # parsing the output of "flatpak uninstall --unused" with simulated "n".
    result = subprocess.run(
        ["flatpak", "list", "--unused"],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode == 0:
        stdout = result.stdout if isinstance(result.stdout, str) else ""
        for line in stdout.splitlines():
            ls = line.strip()
            if ls:
                names.append(ls)
    elif result.stderr and "unknown option" in result.stderr.lower():
        # Fallback for older flatpak versions (< 1.14):
        # uninstall --unused outputs the list before asking confirmation.
        # Pipe "n" to prevent actual removal.
        result = subprocess.run(
            ["flatpak", "uninstall", "--unused"],
            capture_output=True,
            text=True,
            env=env,
            input="n\n",
        )
        stdout = result.stdout if isinstance(result.stdout, str) else ""
        for line in stdout.splitlines():
            ls = line.strip()
            m = re.match(r"\s*\d+\.\s+(.+)", ls)
            if m:
                names.append(m.group(1))
        if not names and result.returncode != 0:
            stderr = result.stderr if isinstance(result.stderr, str) else ""
            if stderr:
                raise RuntimeError(stderr.strip())
    else:
        stderr = result.stderr if isinstance(result.stderr, str) else ""
        msg = stderr.strip() or f"flatpak list --unused exited with code {result.returncode}"
        raise RuntimeError(msg)

    sizes: dict[str, int] = {}
    if names:
        for name in names:
            info = subprocess.run(
                ["flatpak", "info", name, "--show-size"],
                capture_output=True,
                text=True,
                env=env,
            )
            if info.returncode == 0:
                for line in info.stdout.splitlines():
                    ls = line.strip().lower()
                    if ls.startswith("installed size:"):
                        val = line.split(":", 1)[-1].strip()
                        sizes[name] = _parse_human_size(val)
                        break

    packages = [
        _make_package(
            name=n,
            size=sizes.get(n, 0),
            desc="Unused Flatpak runtime",
            type_tag="flatpak",
        )
        for n in names
    ]
    return _sort_by_size_desc(packages)


def get_broken_packages() -> list[PackageDict]:
    if not shutil.which("pacman"):
        return []
    result = subprocess.run(["pacman", "-Qk"], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    names: list[str] = []
    descs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "missing" in line or "ERROR" in line:
            name = line.split(":")[0].strip()
            desc = line.split(":", 1)[-1].strip() if ":" in line else "Broken package"
            names.append(name)
            descs[name] = desc

    sizes = [0] * len(names)
    if names and shutil.which("expac"):
        size_result = subprocess.run(
            ["expac", "-Q", "%m"] + names,
            capture_output=True,
            text=True,
        )
        if size_result.returncode == 0:
            seen = size_result.stdout.splitlines()
            for i in range(min(len(seen), len(names))):
                s = seen[i].strip()
                sizes[i] = int(s) if s.isdigit() else 0

    packages = [
        _make_package(name=n, size=s, desc=descs[n], type_tag="broken")
        for n, s in zip(names, sizes, strict=True)
    ]
    return _sort_by_size_desc(packages)


def get_aur_build_deps() -> list[PackageDict]:
    orphans = _get_orphan_names()
    if not orphans:
        return []
    aur_pkgs = get_aur_packages()
    if not aur_pkgs:
        return []

    packages: list[PackageDict] = []
    for pkg in _query_expac(orphans):
        if pkg["name"].lower() in aur_pkgs:
            packages.append(
                _make_package(
                    name=pkg["name"],
                    size=pkg["size"],
                    desc="Unused AUR build dependency",
                    type_tag="aur-dep",
                )
            )

    return _sort_by_size_desc(packages)


def get_aur_cache_packages() -> list[PackageDict]:
    """Show cached AUR build sources from yay/paru."""
    packages: list[PackageDict] = []
    seen_names: set[str] = set()

    def scan_cache_root(root: Path) -> None:
        if root.exists():
            for d in sorted(root.iterdir()):
                if d.is_dir() and d.name not in seen_names:
                    seen_names.add(d.name)
                    try:
                        total = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                    except OSError:
                        total = 0
                    packages.append(
                        _make_package(
                            name=d.name,
                            size=total,
                            desc="AUR build source",
                            type_tag="aur-cache",
                        )
                    )

    # yay stores package sources directly under ~/.cache/yay/<pkg>/
    scan_cache_root(Path.home() / ".cache" / "yay")

    # paru stores clones under ~/.cache/paru/clone/<pkg>/
    paru_cache = Path.home() / ".cache" / "paru"
    if paru_cache.exists():
        paru_root = paru_cache / "clone"
        if not paru_root.exists():
            paru_root = paru_cache  # fallback for older paru versions
        scan_cache_root(paru_root)

    return _sort_by_size_desc(packages)


def get_steam_library_paths() -> list[Path]:
    """Discover all Steam library folders from libraryfolders.vdf.

    Supports both old/new VDF formats. Falls back to the default
    ~/.steam/steam path if the VDF file is missing.
    """
    default_steam = Path.home() / ".steam" / "steam"
    vdf_path = default_steam / "steamapps" / "libraryfolders.vdf"

    if not vdf_path.exists():
        return [default_steam] if default_steam.exists() else []

    try:
        text = vdf_path.read_text()
    except OSError:
        return [default_steam] if default_steam.exists() else []

    paths = []
    # Newer VDF format: "path" "<value>" inside numbered blocks
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        paths.append(Path(m.group(1)))
    # Older VDF format: "<index>" "<value>" as direct value
    if not paths:
        for m in re.finditer(r'"(\d+)"\s+"([^"]+)"', text):
            paths.append(Path(m.group(2)))

    # Ensure default path is always included (it may not appear in VDF)
    seen = {p.resolve() for p in paths}
    if default_steam.resolve() not in seen and default_steam.exists():
        paths.insert(0, default_steam)

    return paths


def get_orphaned_proton_prefixes() -> list[PackageDict]:
    library_paths = get_steam_library_paths()
    if not library_paths:
        return []

    installed: set[str] = set()
    for lib_path in library_paths:
        for mf in (lib_path / "steamapps").glob("appmanifest_*.acf"):
            try:
                text = mf.read_text()
                for line in text.splitlines():
                    ls = line.strip()
                    if ls.startswith('"appid"'):
                        appid = ls.split('"')[3] if ls.count('"') >= 4 else ""
                        if appid.isdigit():
                            installed.add(appid)
                        break
            except OSError:
                continue

    packages: list[PackageDict] = []
    seen_appids: set[str] = set()
    for lib_path in library_paths:
        compatdata = lib_path / "steamapps" / "compatdata"
        if not compatdata.exists():
            continue
        for d in compatdata.iterdir():
            if not d.is_dir() or not d.name.isdigit():
                continue
            if d.name in seen_appids or d.name in installed:
                continue
            seen_appids.add(d.name)
            try:
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            except OSError:
                size = 0
            packages.append(
                _make_package(
                    name=d.name,
                    size=size,
                    desc="Orphaned Proton prefix",
                    type_tag="proton-prefix",
                )
            )

    return _sort_by_size_desc(packages)


def get_obsolete_steam_runtimes() -> list[PackageDict]:
    library_paths = get_steam_library_paths()
    if not library_paths:
        return []

    installed_stems: set[str] = set()
    for lib_path in library_paths:
        for mf in (lib_path / "steamapps").glob("appmanifest_*.acf"):
            try:
                text = mf.read_text()
                for line in text.splitlines():
                    ls = line.strip()
                    if ls.startswith('"installdir"'):
                        dirname = ls.split('"')[3] if ls.count('"') >= 4 else ""
                        if dirname:
                            installed_stems.add(dirname.lower())
                        break
            except OSError:
                continue

    packages: list[PackageDict] = []
    seen_names: set[str] = set()
    runtime_keywords = (
        "proton",
        "steamlinuxruntime",
        "steam run",
        "runtime",
        "sdk",
        "redistributable",
        "linux runtime",
    )

    for lib_path in library_paths:
        common_dir = lib_path / "steamapps" / "common"
        if not common_dir.exists():
            continue
        for d in common_dir.iterdir():
            if not d.is_dir():
                continue
            name_lower = d.name.lower()
            if not any(kw in name_lower for kw in runtime_keywords):
                continue
            if name_lower in installed_stems:
                continue
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            try:
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            except OSError:
                size = 0
            packages.append(
                _make_package(
                    name=d.name,
                    size=size,
                    desc="Obsolete Steam runtime",
                    type_tag="steam-runtime",
                )
            )

    return _sort_by_size_desc(packages)


def _scan_runner_dir(root: Path, prefix: str, desc: str, sep: str = ":") -> list[PackageDict]:
    if not root.exists():
        return []
    packages: list[PackageDict] = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        try:
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        except OSError:
            size = 0
        packages.append(
            _make_package(
                name=f"{prefix}{sep}{d.name}",
                size=size,
                desc=desc,
                type_tag="launcher-runner",
            )
        )
    return packages


def get_ollama_models() -> list[PackageDict]:
    """Fetch locally installed Ollama models via `ollama list`."""
    if not shutil.which("ollama"):
        return []

    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if result.returncode != 0:
        msg = result.stderr.strip() or f"ollama list exited with code {result.returncode}"
        raise RuntimeError(msg)

    packages: list[PackageDict] = []
    lines = result.stdout.splitlines()
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        name = parts[0]
        # ollama list SIZE column is two tokens: number + unit, e.g. "1.2" "GB"
        size_str = f"{parts[2]} {parts[3]}"
        size = _parse_human_size(size_str)
        packages.append(_make_package(name=name, size=size, desc="Ollama model", type_tag="ollama"))

    return _sort_by_size_desc(packages)


def _get_runner_roots() -> list[tuple[Path, str, str, str]]:
    """Return (root_dir, name_prefix, description, separator) for all known runner locations."""
    roots = [
        # Native installs
        (Path.home() / ".local" / "share" / "lutris" / "runners", "lutris", "Lutris runner", ":"),
        (
            Path.home() / ".local" / "share" / "bottles" / "runners",
            "bottles",
            "Bottles runner",
            ":",
        ),
    ]
    for rt in ("wine", "proton"):
        roots.append(
            (
                Path.home() / ".config" / "heroic" / "tools" / "runners" / rt,
                f"heroic:{rt}",
                "Heroic runner",
                "/",
            )
        )

    # Flatpak installs
    var = Path.home() / ".var" / "app"
    flatpak_map = {
        "net.lutris.Lutris": ("lutris", "Lutris runner"),
        "com.usebottles.bottles": ("bottles", "Bottles runner"),
        "com.heroicgameslauncher.hgl": ("heroic", "Heroic runner"),
    }
    for app_id, (prefix, desc) in flatpak_map.items():
        base = var / app_id
        if app_id == "com.heroicgameslauncher.hgl":
            for rt in ("wine", "proton"):
                roots.append(
                    (
                        base / "config" / "heroic" / "tools" / "runners" / rt,
                        f"{prefix}:{rt}",
                        desc,
                        "/",
                    )
                )
        elif app_id == "net.lutris.Lutris":
            roots.append((base / "data" / "lutris" / "runners", prefix, desc, ":"))
        elif app_id == "com.usebottles.bottles":
            roots.append((base / "data" / "bottles" / "runners", prefix, desc, ":"))

    return roots


def get_stale_launcher_runners() -> list[PackageDict]:
    packages: list[PackageDict] = []
    seen_names: set[str] = set()
    for root, prefix, desc, sep in _get_runner_roots():
        for pkg in _scan_runner_dir(root, prefix, desc, sep):
            if pkg["name"] not in seen_names:
                seen_names.add(pkg["name"])
                packages.append(pkg)
    return _sort_by_size_desc(packages)


def get_npm_cache_packages() -> list[PackageDict]:
    """Read-only scan: report npm cache size as reclaimable space."""
    if not shutil.which("npm"):
        return []

    result = subprocess.run(["npm", "config", "get", "cache"], capture_output=True, text=True)
    if result.returncode != 0:
        return []

    cache_dir = Path(result.stdout.strip())
    if not cache_dir.exists():
        return []

    try:
        total = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
    except OSError:
        total = 0

    if total == 0:
        return []

    return [
        _make_package(
            name="npm-cache",
            size=total,
            desc=f"npm package cache ({cache_dir})",
            type_tag="npm-cache",
        )
    ]


def get_stale_node_modules() -> list[PackageDict]:
    """Read-only scan: find node_modules orphaned by deleted/moved projects."""
    scan_dirs = [
        Path.home() / "Projects",
        Path.home() / "dev",
        Path.home() / "src",
        Path.home() / "workspace",
        Path.home() / "code",
    ]

    packages: list[PackageDict] = []
    seen_names: set[str] = set()
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        try:
            for d in scan_dir.iterdir():
                if not d.is_dir():
                    continue
                if d.name in seen_names:
                    continue
                node_modules = d / "node_modules"
                if not node_modules.is_dir():
                    continue
                # Project is considered alive if it has a package.json
                if (d / "package.json").exists():
                    continue
                seen_names.add(d.name)
                try:
                    size = sum(f.stat().st_size for f in node_modules.rglob("*") if f.is_file())
                except OSError:
                    size = 0
                packages.append(
                    _make_package(
                        name=d.name,
                        size=size,
                        desc="Stale node_modules (project missing package.json)",
                        type_tag="npm-stale",
                    )
                )
        except OSError:
            continue

    return _sort_by_size_desc(packages)

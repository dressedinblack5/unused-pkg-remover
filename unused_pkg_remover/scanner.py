import os
import re
import shutil
import subprocess
from pathlib import Path

from .constants import _CACHE_ARCHES, _CACHE_EXTS


def get_ignored_packages() -> set[str]:
    ignored = set()
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


def _query_expac(package_names: list[str]) -> list[dict]:
    cmd = ["expac", "-Q", "%n|%l|%d|%m"] + package_names
    result = subprocess.run(cmd, capture_output=True, text=True)
    packages = []
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 4:
            name, date, desc, size_str = parts
            try:
                size = int(size_str.strip())
            except ValueError:
                size = 0
            packages.append(
                {
                    "name": name,
                    "date": date,
                    "desc": desc,
                    "size": size,
                }
            )
    packages.sort(key=lambda x: x["size"], reverse=True)
    return packages


def get_unused_packages() -> tuple[list[dict], int]:
    if not shutil.which("expac"):
        raise RuntimeError("expac not found. Install it: sudo pacman -S expac")

    orphans = _get_orphan_names()
    if not orphans:
        return [], 0

    ignored = get_ignored_packages() | get_explicitly_installed_packages()
    aur_pkgs = get_aur_packages()

    unused = []
    filtered_count = 0
    for pkg in _query_expac(orphans):
        if pkg["name"].lower() in ignored:
            filtered_count += 1
            continue
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
    """Return {name, extracted, size, installed} for each pacman cache file."""
    cache_dir = Path("/var/cache/pacman/pkg")
    if not cache_dir.exists():
        return []
    installed = _get_installed_packages()
    entries = []
    for f in cache_dir.iterdir():
        if not f.is_file() or not any(f.name.endswith(ext) for ext in _CACHE_EXTS):
            continue
        extracted = _extract_cache_pkg_name(f.name)
        entries.append(
            {"name": f.name, "extracted": extracted, "size": f.stat().st_size, "installed": extracted in installed}
        )
    return entries


def get_cache_packages() -> list[dict]:
    """Cached packages not currently installed, grouped by package name."""
    by_name: dict[str, list[dict]] = {}
    for e in _iter_cache_entries():
        by_name.setdefault(e["extracted"], []).append(e)
    packages = [
        {
            "name": name,
            "size": sum(e["size"] for e in entries),
            "desc": f"{len(entries)} cached version(s), not installed",
            "type_tag": "cache",
        }
        for name, entries in by_name.items()
        if not entries[0]["installed"]
    ]
    packages.sort(key=lambda x: x["size"], reverse=True)
    return packages


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


def get_unused_flatpaks() -> list[dict]:
    if not shutil.which("flatpak"):
        return []
    env = {**os.environ, "LANG": "C"}
    result = subprocess.run(
        ["flatpak", "uninstall", "--unused", "--noninteractive"],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        msg = (
            result.stderr.strip()
            or f"flatpak uninstall --unused exited with code {result.returncode}"
        )
        raise RuntimeError(msg)
    names = []
    for line in result.stdout.splitlines():
        ls = line.strip()
        if ls and not ls.startswith("These") and ls != "Nothing unused to uninstall":
            names.append(ls)

    sizes = {}
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
        {
            "name": n,
            "size": sizes.get(n, 0),
            "desc": "Unused Flatpak runtime",
            "type_tag": "flatpak",
        }
        for n in names
    ]
    return packages


def get_broken_packages() -> list[dict]:
    if not shutil.which("pacman"):
        return []
    result = subprocess.run(["pacman", "-Qk"], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    names = []
    descs = {}
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
        {"name": n, "size": s, "desc": descs[n], "type_tag": "broken"}
        for n, s in zip(names, sizes, strict=True)
    ]
    return packages


def get_aur_build_deps() -> list[dict]:
    orphans = _get_orphan_names()
    if not orphans:
        return []
    aur_pkgs = get_aur_packages()
    if not aur_pkgs:
        return []

    packages = []
    for pkg in _query_expac(orphans):
        if pkg["name"].lower() in aur_pkgs:
            packages.append(
                {
                    "name": pkg["name"],
                    "size": pkg["size"],
                    "desc": "Unused AUR build dependency",
                    "type_tag": "aur-dep",
                }
            )

    return packages


def get_all_cache_packages() -> list[dict]:
    """Every cache file including installed versions (one row per file)."""
    packages = [
        {
            "name": e["name"],
            "size": e["size"],
            "desc": "installed" if e["installed"] else "not installed",
            "type_tag": "cache",
        }
        for e in _iter_cache_entries()
    ]
    packages.sort(key=lambda x: x["size"], reverse=True)
    return packages


def get_aur_cache_packages() -> list[dict]:
    """Show cached AUR build sources from yay/paru."""
    packages = []
    for cache_root in [Path.home() / ".cache" / "yay", Path.home() / ".cache" / "paru"]:
        if not cache_root.exists():
            continue
        for d in sorted(cache_root.iterdir()):
            if d.is_dir():
                try:
                    total = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                except OSError:
                    total = 0
                packages.append(
                    {
                        "name": d.name,
                        "size": total,
                        "desc": "AUR build source",
                        "type_tag": "aur-cache",
                    }
                )

    packages.sort(key=lambda x: x["size"], reverse=True)
    return packages


def get_orphaned_proton_prefixes() -> list[dict]:
    steam_dir = Path.home() / ".steam" / "steam"
    compatdata = steam_dir / "steamapps" / "compatdata"
    if not compatdata.exists():
        return []

    installed = set()
    for mf in (steam_dir / "steamapps").glob("appmanifest_*.acf"):
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

    packages = []
    for d in compatdata.iterdir():
        if not d.is_dir() or not d.name.isdigit():
            continue
        if d.name not in installed:
            try:
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            except OSError:
                size = 0
            packages.append(
                {
                    "name": d.name,
                    "size": size,
                    "desc": "Orphaned Proton prefix",
                    "type_tag": "proton-prefix",
                }
            )

    packages.sort(key=lambda x: x["size"], reverse=True)
    return packages


def get_obsolete_steam_runtimes() -> list[dict]:
    common_dir = Path.home() / ".steam" / "steam" / "steamapps" / "common"
    if not common_dir.exists():
        return []

    steam_dir = common_dir.parent.parent
    appmanifests = list((steam_dir / "steamapps").glob("appmanifest_*.acf"))
    installed_stems: set[str] = set()
    for mf in appmanifests:
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

    packages = []
    runtime_keywords = (
        "proton",
        "steamlinuxruntime",
        "steam run",
        "runtime",
        "sdk",
        "redistributable",
        "linux runtime",
    )

    for d in common_dir.iterdir():
        if not d.is_dir():
            continue
        name_lower = d.name.lower()
        if not any(kw in name_lower for kw in runtime_keywords):
            continue
        if name_lower in installed_stems:
            continue

        try:
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        except OSError:
            size = 0
        packages.append(
            {
                "name": d.name,
                "size": size,
                "desc": "Obsolete Steam runtime",
                "type_tag": "steam-runtime",
            }
        )

    packages.sort(key=lambda x: x["size"], reverse=True)
    return packages


def _scan_runner_dir(root: Path, prefix: str, desc: str, sep: str = ":") -> list[dict]:
    if not root.exists():
        return []
    packages = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        try:
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        except OSError:
            size = 0
        packages.append(
            {
                "name": f"{prefix}{sep}{d.name}",
                "size": size,
                "desc": desc,
                "type_tag": "launcher-runner",
            }
        )
    return packages


def get_ollama_models() -> list[dict]:
    """Fetch locally installed Ollama models via `ollama list`."""
    if not shutil.which("ollama"):
        return []

    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if result.returncode != 0:
        msg = result.stderr.strip() or f"ollama list exited with code {result.returncode}"
        raise RuntimeError(msg)

    packages = []
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
        packages.append(
            {
                "name": name,
                "size": size,
                "desc": "Ollama model",
                "type_tag": "ollama",
            }
        )

    packages.sort(key=lambda x: x["size"], reverse=True)
    return packages


def get_stale_launcher_runners() -> list[dict]:
    packages = []
    packages.extend(
        _scan_runner_dir(
            Path.home() / ".local" / "share" / "lutris" / "runners", "lutris", "Lutris runner"
        )
    )
    for rt in ("wine", "proton"):
        packages.extend(
            _scan_runner_dir(
                Path.home() / ".config" / "heroic" / "tools" / "runners" / rt,
                f"heroic:{rt}",
                "Heroic runner",
                sep="/",
            )
        )
    packages.extend(
        _scan_runner_dir(
            Path.home() / ".local" / "share" / "bottles" / "runners", "bottles", "Bottles runner"
        )
    )
    packages.sort(key=lambda x: x["size"], reverse=True)
    return packages

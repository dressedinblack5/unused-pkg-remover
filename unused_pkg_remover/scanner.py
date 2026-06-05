import os
import re
import shutil
import subprocess
from pathlib import Path


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


SAFE_PACKAGES = {
    "acl",
    "alsa-plugins",
    "alsa-utils",
    "amd-ucode",
    "archlinux-keyring",
    "bash",
    "bash-completion",
    "bluez",
    "bluez-utils",
    "btrfs-progs",
    "ca-certificates",
    "ca-certificates-utils",
    "chromium",
    "cups",
    "coreutils",
    "cryptsetup",
    "curl",
    "dbus",
    "dhcpcd",
    "diffutils",
    "docker",
    "dosfstools",
    "e2fsprogs",
    "efibootmgr",
    "exfatprogs",
    "fakeroot",
    "file",
    "filesystem",
    "findutils",
    "firefox",
    "firewalld",
    "fish",
    "flatpak",
    "fuse2",
    "fuse3",
    "fwupd",
    "gawk",
    "gcc-libs",
    "gdm",
    "glibc",
    "gnome-shell",
    "grep",
    "grub",
    "gzip",
    "hwdata",
    "inetutils",
    "intel-ucode",
    "iproute2",
    "iputils",
    "iw",
    "iwd",
    "kmod",
    "less",
    "libcap",
    "libidn2",
    "libnl",
    "libpcap",
    "libpng",
    "libusb",
    "libutil-linux",
    "licenses",
    "lightdm",
    "linux",
    "linux-firmware",
    "linux-lts",
    "logrotate",
    "lutris",
    "lvm2",
    "lz4",
    "lzo",
    "man-db",
    "man-pages",
    "mdadm",
    "mesa",
    "mkinitcpio",
    "nano",
    "ncurses",
    "netctl",
    "networkmanager",
    "nftables",
    "nspr",
    "nss",
    "ntp",
    "openresolv",
    "openssh",
    "openssl",
    "os-prober",
    "pacman",
    "pacman-mirrorlist",
    "pam",
    "pambase",
    "parted",
    "pciutils",
    "pcmciautils",
    "perl",
    "pinentry",
    "pipewire",
    "pkg-config",
    "plasma-desktop",
    "podman",
    "polkit",
    "procps-ng",
    "psmisc",
    "pulseaudio",
    "python",
    "reiserfsprogs",
    "rsync",
    "s-nail",
    "sddm",
    "sed",
    "shadow",
    "sqlite",
    "steam",
    "sudo",
    "sysfsutils",
    "systemd",
    "systemd-libs",
    "systemd-resolvconf",
    "systemd-sysvcompat",
    "tar",
    "texinfo",
    "thin-provisioning-tools",
    "thunderbird",
    "timezone",
    "tpm2-tss",
    "tzdata",
    "usbutils",
    "util-linux",
    "vi",
    "vim",
    "wget",
    "which",
    "wine",
    "wireless-regdb",
    "wireless-tools",
    "wireplumber",
    "wpa_supplicant",
    "xfce4-meta",
    "xfsprogs",
    "xz",
    "zerofree",
    "zlib",
    "zsh",
    "zstd",
}


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


def get_unused_packages() -> tuple[list[dict], int]:
    if not shutil.which("expac"):
        raise RuntimeError("expac not found. Install it: sudo pacman -S expac")

    orphans = _get_orphan_names()
    if not orphans:
        return [], 0

    ignored = get_ignored_packages() | SAFE_PACKAGES | get_explicitly_installed_packages()
    aur_pkgs = get_aur_packages()

    cmd = ["expac", "-Q", "%n|%i|%d|%m"] + orphans
    result = subprocess.run(cmd, capture_output=True, text=True)

    unused = []
    filtered_count = 0
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 4:
            name, date, desc, size_str = parts
            if name.lower() in ignored:
                filtered_count += 1
                continue
            try:
                size = int(size_str)
            except ValueError:
                size = 0
            unused.append(
                {
                    "name": name,
                    "date": date,
                    "desc": desc,
                    "size": size,
                    "is_aur": name.lower() in aur_pkgs,
                }
            )

    unused.sort(key=lambda x: x["size"], reverse=True)
    return unused, filtered_count


_CACHE_EXTS = (".pkg.tar.zst", ".pkg.tar.xz", ".pkg.tar.gz", ".pkg.tar.bz2")
_CACHE_ARCHES = ("-x86_64", "-any", "-i686", "-aarch64")


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


def get_cache_packages() -> list[dict]:
    cache_dir = Path("/var/cache/pacman/pkg")
    if not cache_dir.exists():
        return []

    installed = _get_installed_packages()

    by_name: dict[str, list[Path]] = {}
    for f in cache_dir.iterdir():
        if not f.is_file():
            continue
        stem = f.name
        for ext in _CACHE_EXTS:
            if stem.endswith(ext):
                stem = stem[: -len(ext)]
                break
        for arch in _CACHE_ARCHES:
            if stem.endswith(arch):
                stem = stem[: -len(arch)]
                break
        last_hyphen = stem.rfind("-")
        if last_hyphen > 0 and stem[last_hyphen + 1 :].isdigit():
            stem = stem[:last_hyphen]
        parts = stem.split("-")
        for i in range(len(parts), 0, -1):
            candidate = "-".join(parts[:i]).lower()
            if candidate in installed:
                by_name.setdefault(candidate, []).append(f)
                break
        else:
            by_name.setdefault(parts[0].lower(), []).append(f)

    packages = []
    for name_lower, files in by_name.items():
        if name_lower in installed:
            continue
        total_size = sum(f.stat().st_size for f in files)
        packages.append(
            {
                "name": name_lower,
                "size": total_size,
                "desc": f"{len(files)} cached version(s), not installed",
                "type_tag": "cache",
            }
        )
    return packages


def get_unused_flatpaks() -> list[dict]:
    if not shutil.which("flatpak"):
        return []
    result = subprocess.run(
        ["flatpak", "uninstall", "--unused", "--noninteractive", "--dry-run"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    names = []
    for line in result.stdout.splitlines():
        ls = line.strip()
        if ls and not ls.startswith("These"):
            names.append(ls)

    sizes = {}
    if names:
        size_result = subprocess.run(
            ["flatpak", "info"] + names + ["--show-size"],
            capture_output=True,
            text=True,
        )
        if size_result.returncode == 0:
            for line_num, line in enumerate(size_result.stdout.splitlines()):
                s = line.strip()
                if s.isdigit() and line_num < len(names):
                    sizes[names[line_num]] = int(s)

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
            sizes = [
                int(s.strip()) if s.strip().isdigit() else 0
                for s in size_result.stdout.splitlines()
            ]

    packages = [
        {"name": n, "size": s, "desc": descs[n], "type_tag": "broken"}
        for n, s in zip(names, sizes, strict=False)
    ]
    return packages


def get_aur_build_deps() -> list[dict]:
    orphans = _get_orphan_names()
    if not orphans:
        return []
    aur_pkgs = get_aur_packages()
    if not aur_pkgs:
        return []

    cmd = ["expac", "-Q", "%n|%i|%d|%m"] + orphans
    result = subprocess.run(cmd, capture_output=True, text=True)

    packages = []
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 4:
            name, date, desc, size_str = parts
            if name.lower() in aur_pkgs:
                packages.append(
                    {
                        "name": name,
                        "size": int(size_str) if size_str.isdigit() else 0,
                        "desc": "Unused AUR build dependency",
                        "type_tag": "aur-dep",
                    }
                )

    packages.sort(key=lambda x: x["size"], reverse=True)
    return packages


def get_all_cache_packages() -> list[dict]:
    """Show every cached package file including installed versions."""
    cache_dir = Path("/var/cache/pacman/pkg")
    if not cache_dir.exists():
        return []

    installed = _get_installed_packages()

    packages = []
    for f in cache_dir.iterdir():
        if not f.is_file() or not any(f.name.endswith(ext) for ext in _CACHE_EXTS):
            continue

        name = f.name
        for ext in _CACHE_EXTS:
            if name.endswith(ext):
                name = name[: -len(ext)]
                break

        is_installed = False
        # Guess package name from stem: strip arch + version
        stem = name.lower()
        for arch in _CACHE_ARCHES:
            if stem.endswith(arch):
                stem = stem[: -len(arch)]
                break
        ver_end = stem.rfind("-")
        if ver_end > 0:
            stem = stem[:ver_end]
        if stem in installed:
            is_installed = True

        size = f.stat().st_size
        packages.append(
            {
                "name": name,
                "size": size,
                "desc": "installed" if is_installed else "not installed",
                "type_tag": "cache",
            }
        )

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

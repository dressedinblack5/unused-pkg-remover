import re
import shutil
import subprocess
from pathlib import Path


def get_ignored_packages():
    ignored = set()
    paths = [
        Path.home() / ".unused-ignore",
        Path.home() / ".config" / "unused-pkg-remover" / "ignore",
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


def get_aur_packages():
    result = subprocess.run(["pacman", "-Qqm"], capture_output=True, text=True)
    if result.returncode != 0:
        return set()
    return {pkg.lower() for pkg in result.stdout.splitlines()}


def get_explicitly_installed_packages():
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


def get_dependents(pkg_name):
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
        result = subprocess.run(["pacman", "-Qi", pkg_name], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                ls = line.strip()
                if ls.startswith("Required By") or ls.startswith("Optional For"):
                    val = ls.split(":", 1)[-1].strip()
                    if val and val != "None":
                        deps.append(val)
                elif ls.startswith("Optional Deps"):
                    break
    return deps


def get_unused_packages():
    if not shutil.which("expac"):
        raise RuntimeError("expac not found. Install it: sudo pacman -S expac")

    cmd = ["pacman", "-Qtdq"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return [], 0

    orphans = result.stdout.splitlines()
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

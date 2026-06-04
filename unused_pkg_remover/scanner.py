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

SAFE_PACKAGES = {
    'acl', 'alsa-plugins', 'alsa-utils', 'archlinux-keyring',
    'bash', 'bash-completion',
    'btrfs-progs', 'ca-certificates', 'ca-certificates-utils',
    'coreutils', 'cryptsetup', 'curl', 'dbus', 'dhcpcd',
    'diffutils', 'dosfstools', 'e2fsprogs', 'efibootmgr',
    'exfatprogs', 'fakeroot', 'file', 'filesystem', 'findutils',
    'fuse2', 'fuse3', 'gawk', 'gcc-libs', 'glibc',
    'grep', 'grub', 'gzip', 'hwdata', 'inetutils',
    'iproute2', 'iputils', 'iw', 'iwd', 'kmod',
    'less', 'libcap', 'libidn2', 'libnl', 'libpcap',
    'libpng', 'libusb', 'libutil-linux', 'licenses', 'linux',
    'linux-firmware', 'linux-lts', 'logrotate', 'lvm2',
    'lz4', 'lzo', 'man-db', 'man-pages', 'mdadm',
    'mkinitcpio', 'nano', 'ncurses', 'netctl', 'networkmanager',
    'nftables', 'nspr', 'nss', 'ntp', 'openresolv',
    'openssh', 'openssl', 'os-prober', 'pacman', 'pacman-mirrorlist',
    'pam', 'pambase', 'parted', 'pciutils', 'pcmciautils',
    'perl', 'pinentry', 'pkg-config', 'polkit', 'procps-ng',
    'psmisc', 'pulseaudio', 'python', 'reiserfsprogs',
    'rsync', 's-nail', 'sed', 'shadow', 'sqlite',
    'sudo', 'sysfsutils', 'systemd', 'systemd-libs',
    'systemd-resolvconf', 'systemd-sysvcompat', 'tar', 'texinfo',
    'thin-provisioning-tools', 'timezone', 'tpm2-tss',
    'tzdata', 'usbutils', 'util-linux',
    'vi', 'vim', 'wget', 'which', 'wireless-regdb',
    'wireless-tools', 'wpa_supplicant', 'xfsprogs',
    'xz', 'zerofree', 'zlib', 'zstd',
}

FILTERED_COUNT = 0


def get_unused_packages():
    global FILTERED_COUNT
    result = subprocess.run(["pacman", "-Qtdq"], capture_output=True, text=True)
    if result.returncode != 0:
        return []

    orphans = result.stdout.splitlines()
    if not orphans:
        return []

    ignored = get_ignored_packages() | SAFE_PACKAGES
    aur_pkgs = get_aur_packages()

    cmd = ["expac", "-Q", "%n|%i|%d|%m"] + orphans
    result = subprocess.run(cmd, capture_output=True, text=True)

    unused = []
    FILTERED_COUNT = 0
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 4:
            name, date, desc, size_str = parts
            if name.lower() in ignored:
                FILTERED_COUNT += 1
                continue
            try:
                size = int(size_str)
            except ValueError:
                size = 0
            unused.append({
                'name': name,
                'date': date,
                'desc': desc,
                'size': size,
                'is_aur': name.lower() in aur_pkgs,
            })

    unused.sort(key=lambda x: x['size'], reverse=True)
    return unused

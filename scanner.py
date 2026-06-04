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

def get_unused_packages():
    result = subprocess.run(["pacman", "-Qtdq"], capture_output=True, text=True)
    if result.returncode != 0:
        return []

    orphans = result.stdout.splitlines()
    if not orphans:
        return []

    ignored = get_ignored_packages()
    aur_pkgs = get_aur_packages()

    cmd = ["expac", "-Q", "%n|%i|%d|%m"] + orphans
    result = subprocess.run(cmd, capture_output=True, text=True)

    unused = []
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) == 4:
            name, date, desc, size_str = parts
            if name.lower() in ignored:
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

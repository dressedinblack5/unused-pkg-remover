_CACHE_EXTS = (".pkg.tar.zst", ".pkg.tar.xz", ".pkg.tar.gz", ".pkg.tar.bz2")
_CACHE_ARCHES = ("-x86_64", "-any", "-i686", "-aarch64")


def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"

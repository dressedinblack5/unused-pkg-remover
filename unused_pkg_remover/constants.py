"""Utility constants and formatting functions for the package remover."""

_CACHE_EXTS = (".pkg.tar.zst", ".pkg.tar.xz", ".pkg.tar.gz", ".pkg.tar.bz2")
_CACHE_ARCHES = (
    "-x86_64",
    "-x86_64_v4",
    "-x86_64_v3",
    "-x86_64_v2",
    "-any",
    "-i686",
    "-aarch64",
    "-armv7h",
)


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"

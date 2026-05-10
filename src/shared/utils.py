import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_file_extension(filename: str) -> str:
    return filename.split(".")[-1].lower() if "." in filename else ""


def format_file_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    k = 1024
    sizes = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= k and i < len(sizes) - 1:
        size_bytes /= k
        i += 1
    return f"{size_bytes:.2f} {sizes[i]}"

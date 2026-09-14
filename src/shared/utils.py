import logging
import os
import re
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

# 上传文件以 ``{file_id}_{原始文件名}`` 的形式落盘
_STORED_NAME_RE = re.compile(
    r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})_(.+)$"
)


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


def split_stored_name(name: str) -> Tuple[str, str]:
    """把 ``{file_id}_{原始文件名}`` 拆成 ``(file_id, 原始文件名)``。

    不符合命名约定时原样返回（例如直接解析测试夹具文件）。
    上传文件统一以该形式落盘，解析/展示时都需要把 file_id 前缀去掉，
    否则标题和向量元数据里会混进一串 UUID。
    """
    match = _STORED_NAME_RE.match(Path(name).name)
    if match:
        return match.group(1), match.group(2)
    return Path(name).stem, Path(name).name


def display_title(filename: str) -> str:
    """由存储文件名得到展示用教材标题（去掉 file_id 前缀与扩展名）。"""
    _, original = split_stored_name(filename)
    return Path(original).stem


def resolve_display_title(title: str, filename: str, file_id: str = "") -> str:
    """修正历史数据里"标题就是存储文件名"的情况。

    旧版本把 ``{file_id}_{原名}`` 直接当成标题存了下来，这里在不重新解析的
    前提下换成去掉前缀的干净标题；若是解析器从正文提取的真实标题，则保留。
    """
    stored_stem = Path(filename).stem if filename else ""
    looks_like_storage_name = (
        not title
        or title == stored_stem
        or (bool(file_id) and file_id in title)
    )
    if looks_like_storage_name:
        return display_title(filename) if filename else (title or file_id)
    return title


def ensure_sslkeylogfile_usable() -> None:
    """修掉指向不存在路径的 ``SSLKEYLOGFILE``。

    Python 的 ssl 模块在建立连接前会以追加模式打开 ``SSLKEYLOGFILE``，
    目录不存在时会直接抛 ``FileNotFoundError`` —— 表现为**所有 HTTPS 请求
    全部失败**（例如大模型 API 完全不可用），而错误信息里只提到一个日志文件，
    排查成本很高。这里优先创建目录以保留用户的调试意图，创建不了就清除该变量。
    """
    raw_path = os.environ.get("SSLKEYLOGFILE")
    if not raw_path:
        return

    directory = os.path.dirname(os.path.abspath(raw_path))
    try:
        os.makedirs(directory, exist_ok=True)
        if not os.access(directory, os.W_OK):
            raise OSError(f"目录不可写: {directory}")
    except OSError as exc:
        logger.warning(
            "SSLKEYLOGFILE 指向不可用的路径（%s），已忽略该环境变量以免 HTTPS 请求全部失败",
            exc,
        )
        os.environ.pop("SSLKEYLOGFILE", None)

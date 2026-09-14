from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple

from src.models.textbook import Textbook
from src.shared.utils import display_title, split_stored_name


class BaseParser(ABC):
    """解析器基类"""

    @abstractmethod
    def parse(self, file_path: Path) -> Textbook:
        """解析文件并返回Textbook对象"""
        pass

    def _generate_chapter_id(self, index: int) -> str:
        """生成章节ID"""
        return f"ch_{index:02d}"

    def _textbook_id(self, file_path: Path) -> str:
        """教材 ID：上传时生成的文件 ID（落盘名首段的 UUID）。"""
        return split_stored_name(file_path.name)[0]

    def _extract_title_from_filename(self, file_path: Path) -> str:
        """从文件名提取展示用标题（去掉存储用的 file_id 前缀）。"""
        return display_title(file_path.name)

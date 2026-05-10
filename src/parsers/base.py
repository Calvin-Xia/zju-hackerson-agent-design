from abc import ABC, abstractmethod
from pathlib import Path

from src.models.textbook import Textbook


class BaseParser(ABC):
    """解析器基类"""

    @abstractmethod
    def parse(self, file_path: Path) -> Textbook:
        """解析文件并返回Textbook对象"""
        pass

    def _generate_chapter_id(self, index: int) -> str:
        """生成章节ID"""
        return f"ch_{index:02d}"

    def _extract_title_from_filename(self, file_path: Path) -> str:
        """从文件名提取标题"""
        return file_path.stem

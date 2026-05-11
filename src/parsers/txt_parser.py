import re
import logging
from pathlib import Path
from typing import List, Optional

from src.models.textbook import Chapter, Textbook
from src.parsers.base import BaseParser
from src.parsers.factory import register_parser
from src.parsers.constants import CHAPTER_PATTERNS

logger = logging.getLogger(__name__)


class TxtParser(BaseParser):
    """TXT解析器"""

    def parse(self, file_path: Path) -> Textbook:
        """解析TXT文件"""
        logger.info(f"Parsing TXT: {file_path}")
        
        content = self._read_file(file_path)
        chapters = self._split_into_chapters(content)
        
        if not chapters:
            chapters.append(Chapter(
                chapter_id=self._generate_chapter_id(0),
                title=self._extract_title_from_filename(file_path),
                page_start=0,
                page_end=0,
                content=content,
                char_count=len(content)
            ))
        
        total_chars = sum(ch.char_count for ch in chapters)
        
        return Textbook(
            textbook_id=file_path.stem,
            filename=file_path.name,
            title=self._extract_title_from_filename(file_path),
            total_pages=0,
            total_chars=total_chars,
            chapters=chapters
        )

    def _read_file(self, file_path: Path) -> str:
        """读取文件内容，自动检测编码"""
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        
        for encoding in encodings:
            try:
                return file_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        
        raise ValueError(f"Unable to decode file: {file_path}")

    def _split_into_chapters(self, content: str) -> List[Chapter]:
        """按标题分割章节"""
        lines = content.split('\n')
        chapters: List[Chapter] = []
        
        current_title = ""
        current_content: List[str] = []
        chapter_index = 0
        
        for line in lines:
            stripped = line.strip()
            
            # 检测章节标题
            chapter_title = self._detect_chapter_title(stripped)
            
            if chapter_title:
                # 保存前一章
                if current_content:
                    chapter_content = '\n'.join(current_content).strip()
                    if chapter_content:
                        chapters.append(Chapter(
                            chapter_id=self._generate_chapter_id(chapter_index),
                            title=current_title or f"章节 {chapter_index + 1}",
                            page_start=0,
                            page_end=0,
                            content=chapter_content,
                            char_count=len(chapter_content)
                        ))
                        chapter_index += 1
                
                # 开始新章
                current_title = chapter_title
                current_content = []
            
            else:
                current_content.append(line)
        
        # 保存最后一章
        if current_content:
            chapter_content = '\n'.join(current_content).strip()
            if chapter_content:
                chapters.append(Chapter(
                    chapter_id=self._generate_chapter_id(chapter_index),
                    title=current_title or f"章节 {chapter_index + 1}",
                    page_start=0,
                    page_end=0,
                    content=chapter_content,
                    char_count=len(chapter_content)
                ))
        
        return chapters

    def _detect_chapter_title(self, line: str) -> Optional[str]:
        """检测章节标题"""
        for pattern in CHAPTER_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return line
        return None


# 注册解析器
register_parser("txt", TxtParser)

import re
import logging
from pathlib import Path
from typing import List

from src.models.textbook import Chapter, Textbook
from src.parsers.base import BaseParser
from src.parsers.factory import register_parser

logger = logging.getLogger(__name__)


class MarkdownParser(BaseParser):
    """Markdown解析器"""

    def parse(self, file_path: Path) -> Textbook:
        """解析Markdown文件"""
        logger.info(f"Parsing Markdown: {file_path}")
        
        try:
            content = file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            content = file_path.read_text(encoding='gbk')
        
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

    def _split_into_chapters(self, content: str) -> List[Chapter]:
        """按标题分割章节"""
        lines = content.split('\n')
        chapters: List[Chapter] = []
        
        current_title = ""
        current_content: List[str] = []
        chapter_index = 0
        
        for line in lines:
            # 检测二级标题作为章节分隔
            if re.match(r'^##\s+', line):
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
                current_title = line.lstrip('#').strip()
                current_content = []
            
            # 检测一级标题（如果没有二级标题）
            elif re.match(r'^#\s+', line) and not current_title:
                current_title = line.lstrip('#').strip()
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


# 注册解析器
register_parser("md", MarkdownParser)
register_parser("markdown", MarkdownParser)

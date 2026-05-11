import re
import logging
from pathlib import Path
from typing import List, Optional

import pdfplumber

from src.models.textbook import Chapter, Textbook
from src.parsers.base import BaseParser
from src.parsers.factory import register_parser
from src.parsers.constants import CHAPTER_PATTERNS

logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
    """PDF解析器"""

    def parse(self, file_path: Path) -> Textbook:
        """解析PDF文件"""
        logger.info(f"Parsing PDF: {file_path}")
        
        chapters: List[Chapter] = []
        total_pages = 0
        total_chars = 0
        
        try:
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                
                current_chapter_title = ""
                current_chapter_content = []
                current_page_start = 1
                chapter_index = 0
                
                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        text = page.extract_text() or ""
                        
                        if not text.strip():
                            continue
                        
                        # 检测章节标题
                        chapter_title = self._detect_chapter_title(text)
                        
                        if chapter_title:
                            # 保存前一章
                            if current_chapter_content:
                                content = "\n".join(current_chapter_content)
                                chapters.append(Chapter(
                                    chapter_id=self._generate_chapter_id(chapter_index),
                                    title=current_chapter_title,
                                    page_start=current_page_start,
                                    page_end=page_num - 1,
                                    content=content,
                                    char_count=len(content)
                                ))
                                chapter_index += 1
                                total_chars += len(content)
                            
                            # 开始新章
                            current_chapter_title = chapter_title
                            current_chapter_content = [text]
                            current_page_start = page_num
                        else:
                            current_chapter_content.append(text)
                    
                    except Exception as e:
                        logger.warning(f"Error parsing page {page_num}: {e}")
                        continue
                
                # 保存最后一章
                if current_chapter_content:
                    content = "\n".join(current_chapter_content)
                    chapters.append(Chapter(
                        chapter_id=self._generate_chapter_id(chapter_index),
                        title=current_chapter_title or "未命名章节",
                        page_start=current_page_start,
                        page_end=total_pages,
                        content=content,
                        char_count=len(content)
                    ))
                    total_chars += len(content)
        
        except Exception as e:
            logger.error(f"Failed to parse PDF: {e}")
            raise
        
        # 如果没有检测到章节，将整个文件作为一章
        if not chapters:
            logger.warning("No chapters detected, treating entire file as one chapter")
            try:
                with pdfplumber.open(file_path) as pdf:
                    full_text = ""
                    for page in pdf.pages:
                        text = page.extract_text() or ""
                        full_text += text + "\n"
                    
                    chapters.append(Chapter(
                        chapter_id=self._generate_chapter_id(0),
                        title=self._extract_title_from_filename(file_path),
                        page_start=1,
                        page_end=total_pages,
                        content=full_text,
                        char_count=len(full_text)
                    ))
                    total_chars = len(full_text)
            except Exception as e:
                logger.error(f"Failed to extract full text: {e}")
                raise
        
        return Textbook(
            textbook_id=file_path.stem,
            filename=file_path.name,
            title=self._extract_title_from_filename(file_path),
            total_pages=total_pages,
            total_chars=total_chars,
            chapters=chapters
        )

    def _detect_chapter_title(self, text: str) -> Optional[str]:
        """检测章节标题"""
        lines = text.split("\n")
        
        for line in lines[:5]:  # 只检查前5行
            line = line.strip()
            if not line:
                continue
            
            for pattern in CHAPTER_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    return line
        
        return None


# 注册解析器
register_parser("pdf", PdfParser)

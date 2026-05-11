"""
文档分块模块

实现教材内容分块功能：
- 文本分割
- 元数据保留
- 批量处理
"""

import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from src.models.textbook import Textbook, Chapter

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """文档块"""
    chunk_id: str
    content: str
    textbook_id: str
    textbook_title: str
    chapter_id: str
    chapter_title: str
    page_start: int
    chunk_index: int
    char_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "textbook_id": self.textbook_id,
            "textbook_title": self.textbook_title,
            "chapter_id": self.chapter_id,
            "chapter_title": self.chapter_title,
            "page_start": self.page_start,
            "chunk_index": self.chunk_index,
            "char_count": self.char_count
        }


class TextChunker:
    """文本分块器"""
    
    def __init__(self, chunk_size: int = 600, chunk_overlap: int = 100):
        """
        初始化分块器
        
        Args:
            chunk_size: 块大小（字符数）
            chunk_overlap: 重叠大小（字符数）
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """将文本分割成句子"""
        sentences = re.split(r'(?<=[。！？；\n])', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """将文本分割成段落"""
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        return paragraphs
    
    def chunk_text(self, text: str) -> List[str]:
        """
        将文本分块
        
        Args:
            text: 输入文本
            
        Returns:
            文本块列表
        """
        if len(text) <= self.chunk_size:
            return [text]
        
        sentences = self._split_into_sentences(text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= self.chunk_size:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                if len(sentence) > self.chunk_size:
                    words = list(sentence)
                    temp_chunk = ""
                    for word in words:
                        if len(temp_chunk) + len(word) <= self.chunk_size:
                            temp_chunk += word
                        else:
                            if temp_chunk:
                                chunks.append(temp_chunk.strip())
                            temp_chunk = word
                    if temp_chunk:
                        current_chunk = temp_chunk
                    else:
                        current_chunk = ""
                else:
                    current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        if self.chunk_overlap > 0 and len(chunks) > 1:
            chunks = self._add_overlap(chunks)
        
        return chunks
    
    def _add_overlap(self, chunks: List[str]) -> List[str]:
        """添加重叠"""
        if len(chunks) <= 1:
            return chunks
        
        overlapped_chunks = [chunks[0]]
        
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            current_chunk = chunks[i]
            
            overlap_text = prev_chunk[-self.chunk_overlap:] if len(prev_chunk) > self.chunk_overlap else prev_chunk
            
            new_chunk = overlap_text + current_chunk
            overlapped_chunks.append(new_chunk)
        
        return overlapped_chunks
    
    def chunk_chapter(
        self,
        textbook: Textbook,
        chapter: Chapter
    ) -> List[DocumentChunk]:
        """
        将章节分块
        
        Args:
            textbook: 教材对象
            chapter: 章节对象
            
        Returns:
            文档块列表
        """
        text_chunks = self.chunk_text(chapter.content)
        
        chunks = []
        for i, content in enumerate(text_chunks):
            chunk = DocumentChunk(
                chunk_id=f"{textbook.textbook_id}_{chapter.chapter_id}_chunk_{i}",
                content=content,
                textbook_id=textbook.textbook_id,
                textbook_title=textbook.title,
                chapter_id=chapter.chapter_id,
                chapter_title=chapter.title,
                page_start=chapter.page_start,
                chunk_index=i,
                char_count=len(content)
            )
            chunks.append(chunk)
        
        return chunks
    
    def chunk_textbook(self, textbook: Textbook) -> List[DocumentChunk]:
        """
        将整本教材分块
        
        Args:
            textbook: 教材对象
            
        Returns:
            文档块列表
        """
        all_chunks = []
        
        for chapter in textbook.chapters:
            chapter_chunks = self.chunk_chapter(textbook, chapter)
            all_chunks.extend(chapter_chunks)
        
        logger.info(f"Chunked textbook '{textbook.title}' into {len(all_chunks)} chunks")
        
        return all_chunks


def chunk_textbook(
    textbook: Textbook,
    chunk_size: int = 600,
    chunk_overlap: int = 100
) -> List[DocumentChunk]:
    """
    便捷函数：将教材分块
    
    Args:
        textbook: 教材对象
        chunk_size: 块大小
        chunk_overlap: 重叠大小
        
    Returns:
        文档块列表
    """
    chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return chunker.chunk_textbook(textbook)

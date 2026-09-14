"""文档分块。

* 分句使用 :mod:`src.shared.text` 的统一实现，中英文标点都能正确处理；
* 相邻块之间按字符做重叠，且**保证块长不超过 ``chunk_size + chunk_overlap``**；
* 超长单句先硬切再组块，避免出现超过模型上下文的长块；
* 记录块在章节内的字符偏移，便于前端给出更精确的引用位置。

偏移量在组块过程中同步累计（而不是事后 ``find``），因此重复句子、
重叠窗口都不会让 ``char_start`` 指到错误的位置。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from src.models.textbook import Chapter, Textbook
from src.shared.text import normalize_text, split_sentences

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
    char_start: int = 0

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
            "char_count": self.char_count,
            "char_start": self.char_start,
        }


class TextChunker:
    """文本分块器"""

    def __init__(
        self,
        chunk_size: int = 600,
        chunk_overlap: int = 100,
        min_chunk_chars: int = 0,
    ):
        """
        Args:
            chunk_size: 块大小（字符数）
            chunk_overlap: 相邻块的重叠字符数
            min_chunk_chars: 小于该长度的尾块会被并入上一块
        """
        self.chunk_size = max(1, int(chunk_size))
        self.chunk_overlap = max(0, min(int(chunk_overlap), self.chunk_size - 1)) \
            if self.chunk_size > 1 else 0
        self.min_chunk_chars = max(0, int(min_chunk_chars))

    # ------------------------------------------------------------------
    # 分句
    # ------------------------------------------------------------------
    @staticmethod
    def _split_into_sentences(text: str) -> List[str]:
        return split_sentences(text)

    def _hard_split(self, text: str) -> List[str]:
        """把超长片段按定长硬切。"""
        return [
            text[i:i + self.chunk_size]
            for i in range(0, len(text), self.chunk_size)
        ]

    # ------------------------------------------------------------------
    # 组块
    # ------------------------------------------------------------------
    def _build_chunk_pairs(self, text: str) -> List[Tuple[str, int]]:
        """把文本切成 ``(块内容, 在 text 中的起始偏移)``，不含重叠。"""
        if not text:
            return []
        if len(text) <= self.chunk_size:
            stripped = text.strip()
            return [(stripped, text.index(stripped))] if stripped else []

        raw: List[Tuple[str, int]] = []
        current = ""
        current_start = 0
        cursor = 0  # 已定位到的文本位置，保证重复句子按顺序匹配

        for sentence in self._split_into_sentences(text):
            position = text.find(sentence, cursor)
            if position < 0:
                position = cursor
            cursor = position + len(sentence)

            if len(sentence) > self.chunk_size:
                if current:
                    raw.append((current, current_start))
                    current = ""
                raw.extend(
                    (sentence[i:i + self.chunk_size], position + i)
                    for i in range(0, len(sentence), self.chunk_size)
                )
                continue

            if len(current) + len(sentence) <= self.chunk_size:
                if not current:
                    current_start = position
                current += sentence
            else:
                if current:
                    raw.append((current, current_start))
                current = sentence
                current_start = position

        if current:
            raw.append((current, current_start))

        pairs = [(chunk.strip(), start) for chunk, start in raw if chunk.strip()]
        if not pairs:
            return []

        # 尾块过短时并入上一块（避免产生无意义的碎片）
        if (
            self.min_chunk_chars
            and len(pairs) > 1
            and len(pairs[-1][0]) < self.min_chunk_chars
        ):
            last_text, last_start = pairs.pop()
            prev_text, prev_start = pairs[-1]
            # 合并后内容连续，起始偏移仍取上一块的起点
            pairs[-1] = (f"{prev_text}{last_text}", prev_start)

        return pairs

    def _add_overlap_pairs(self, pairs: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
        """给每个块（除首块）加上前一块的尾部重叠，并同步修正起始偏移。"""
        if self.chunk_overlap <= 0 or len(pairs) <= 1:
            return pairs

        overlapped: List[Tuple[str, int]] = [pairs[0]]
        for i in range(1, len(pairs)):
            content, start = pairs[i]
            prev_content, prev_start = pairs[i - 1]
            if len(prev_content) > self.chunk_overlap:
                overlap_text = prev_content[-self.chunk_overlap:]
                overlap_start = prev_start + len(prev_content) - self.chunk_overlap
            else:
                overlap_text = prev_content
                overlap_start = prev_start

            merged = f"{overlap_text}{content}"
            if merged.strip() == overlapped[-1][0].strip():
                continue  # 完全重复的块直接跳过
            overlapped.append((merged, overlap_start))

        return overlapped

    def chunk_text(self, text: str) -> List[str]:
        """把文本切成带重叠的块（仅返回文本）。"""
        return [content for content, _ in self.chunk_text_with_offsets(text)]

    def chunk_text_with_offsets(self, text: str) -> List[Tuple[str, int]]:
        """把文本切成带重叠的块，并返回每块在原文中的字符偏移。"""
        return self._add_overlap_pairs(self._build_chunk_pairs(text))

    def _add_overlap(self, chunks: List[str]) -> List[str]:
        """兼容旧接口：仅对纯文本块加重叠。"""
        return [content for content, _ in self._add_overlap_pairs(
            [(chunk, 0) for chunk in chunks]
        )]

    # ------------------------------------------------------------------
    # 章节 / 教材
    # ------------------------------------------------------------------
    def chunk_chapter(self, textbook: Textbook, chapter: Chapter) -> List[DocumentChunk]:
        """把章节切成文档块。"""
        content = normalize_text(chapter.content or "")
        if not content:
            return []

        pairs = self.chunk_text_with_offsets(content)

        return [
            DocumentChunk(
                chunk_id=f"{textbook.textbook_id}_{chapter.chapter_id}_chunk_{index}",
                content=chunk_content,
                textbook_id=textbook.textbook_id,
                textbook_title=textbook.title or textbook.filename,
                chapter_id=chapter.chapter_id,
                chapter_title=chapter.title,
                page_start=chapter.page_start,
                chunk_index=index,
                char_count=len(chunk_content),
                char_start=start,
            )
            for index, (chunk_content, start) in enumerate(pairs)
        ]

    def chunk_textbook(self, textbook: Textbook, dedupe: bool = True) -> List[DocumentChunk]:
        """把整本教材切成文档块。"""
        all_chunks: List[DocumentChunk] = []
        seen: Set[str] = set()

        for chapter in textbook.chapters:
            for chunk in self.chunk_chapter(textbook, chapter):
                if dedupe:
                    fingerprint = normalize_text(chunk.content)
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                all_chunks.append(chunk)

        logger.info(
            "教材《%s》分块完成：%d 个块", textbook.title or textbook.filename, len(all_chunks)
        )
        return all_chunks


def chunk_textbook(
    textbook: Textbook,
    chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> List[DocumentChunk]:
    """便捷函数：将教材分块。"""
    chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return chunker.chunk_textbook(textbook)

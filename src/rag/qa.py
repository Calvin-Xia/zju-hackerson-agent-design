"""RAG 问答。

相对旧实现的改进：

* **相关性过滤**：低于阈值的片段直接丢弃，全部不相关时不再调用 LLM，
  直接回答「未找到相关信息」，避免用无关上下文诱导幻觉；
* **近重复去重**：多本教材描述同一内容时只保留最相关的一段，并记录其它来源；
* **来源多样性**：限制同一本教材的最大片段数，避免上下文被一本书占满；
* **上下文预算**：按字数上限裁剪上下文，防止超出模型上下文；
* **引用保证**：Prompt 要求使用 ``[1]`` 形式的编号引用；模型完全漏写时
  自动在末尾补齐来源列表，确保回答不会「无出处」。
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.embedding.service import get_embedding_service
from src.llm.client import LLMError, call_llm
from src.shared.config import settings
from src.shared.text import normalize_text, truncate_at_boundary
from src.vectorstore.faiss_store import get_vector_store

logger = logging.getLogger(__name__)

NO_ANSWER_TEXT = "当前知识库中未找到相关信息"

# 仅在「回答很短」时才认为命中这些措辞，避免长回答里顺带出现
# 「无法确定」等词就把整段答案判为无答案、连带丢掉引用。
_NO_ANSWER_MARKERS = ("未找到相关信息", "未找到", "无法回答", "没有相关信息", "未提及", "无法确定")
_NO_ANSWER_MAX_CHARS = 60

_CITATION_RE = re.compile(r"\[(\d+)\]")


@dataclass
class Citation:
    """引用"""

    chunk_id: str
    textbook: str
    chapter: str
    page: int
    content: str
    relevance_score: float
    duplicate_sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "textbook": self.textbook,
            "chapter": self.chapter,
            "page": self.page,
            "content": self.content,
            "relevance_score": self.relevance_score,
            "duplicate_sources": self.duplicate_sources,
        }


@dataclass
class QAResponse:
    """问答响应"""

    answer: str
    citations: List[Citation]
    source_chunks: List[str]
    retrieved_count: int = 0
    top_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "source_chunks": self.source_chunks,
            "retrieved_count": self.retrieved_count,
            "top_score": self.top_score,
        }


class RAGQuestionAnswerer:
    """RAG 问答器"""

    def __init__(self, top_k: Optional[int] = None):
        self.top_k = int(settings.TOP_K if top_k is None else top_k)
        self.embedding_service = get_embedding_service()
        self.vector_store = get_vector_store()

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def _min_score(self) -> float:
        """相关度下限：显式配置优先，否则按嵌入后端自适应。"""
        if settings.RAG_MIN_SCORE is not None:
            return float(settings.RAG_MIN_SCORE)
        return self.embedding_service.suggested_min_score

    async def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """召回并按相关度过滤片段。"""
        if not query.strip() or self.vector_store.size == 0:
            return []

        query_vector = await asyncio.to_thread(self.embedding_service.encode, query)
        recall_k = max(self.top_k, int(settings.RAG_RECALL_K))
        results = await asyncio.to_thread(self.vector_store.search, query_vector, recall_k)
        if not results:
            return []

        best_score = max(score for _idx, score in results)
        floor = self._min_score()
        threshold = max(floor, best_score * float(settings.RAG_RELATIVE_SCORE_RATIO))

        candidates: List[Dict[str, Any]] = []
        for index, score in results:
            if score < threshold:
                continue
            metadata = self.vector_store.get_metadata(index)
            if metadata:
                candidates.append({"metadata": metadata, "similarity": float(score)})

        if not candidates:
            logger.info(
                "查询「%s」无相关片段（最高分 %.3f < 阈值 %.3f）", query, best_score, threshold
            )
            return []

        selected = self._dedupe_and_diversify(candidates)
        logger.info(
            "检索到 %d 个相关片段（召回 %d，最高分 %.3f，阈值 %.3f）",
            len(selected), len(results), best_score, threshold,
        )
        return selected

    def _dedupe_and_diversify(self, candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """近重复去重 + 单教材片段数限制。"""
        selected: List[Dict[str, Any]] = []
        fingerprints: List[str] = []
        per_textbook: Dict[str, int] = {}
        max_per_textbook = max(1, int(settings.RAG_MAX_CHUNKS_PER_TEXTBOOK))

        for candidate in candidates:
            metadata = candidate["metadata"]
            content = normalize_text(str(metadata.get("content", "")))
            if not content:
                continue

            textbook = str(metadata.get("textbook_title") or metadata.get("textbook_id") or "")

            duplicate_of: Optional[int] = None
            for position, existing in enumerate(fingerprints):
                if self._is_duplicate(content, existing):
                    duplicate_of = position
                    break

            if duplicate_of is not None:
                source_label = f"{textbook}·{metadata.get('chapter_title', '')}"
                selected[duplicate_of]["also_in"].append(source_label)
                continue

            # 没有教材标识时不启用「单教材上限」，否则会把所有片段归到同一个空 key 上
            if textbook and per_textbook.get(textbook, 0) >= max_per_textbook:
                continue

            if textbook:
                per_textbook[textbook] = per_textbook.get(textbook, 0) + 1
            fingerprints.append(content)
            selected.append({"metadata": metadata, "similarity": candidate["similarity"], "also_in": []})

            if len(selected) >= self.top_k:
                break

        return selected

    @staticmethod
    def _is_duplicate(content: str, other: str) -> bool:
        """判断两段内容是否为同一内容的近似重复。"""
        if content == other:
            return True
        shorter, longer = (content, other) if len(content) <= len(other) else (other, content)
        if not shorter:
            return False
        # 短片段被长片段覆盖，或长片段的大部分内容重合
        if shorter in longer:
            return True
        probe = shorter[: min(60, len(shorter))]
        return len(probe) >= 20 and probe in longer

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------
    def _build_context(
        self, context_chunks: Sequence[Dict[str, Any]]
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """拼接上下文，返回 ``(上下文文本, 实际使用的片段)``。

        保证拼接结果不超过 ``RAG_MAX_CONTEXT_CHARS``：每个片段按**剩余预算**
        截断，而不是每块都按总预算截断（旧实现会让总长度超出上限数倍）。
        """
        budget = max(500, int(settings.RAG_MAX_CONTEXT_CHARS))
        parts: List[str] = []
        used: List[Dict[str, Any]] = []
        used_chars = 0

        for position, chunk in enumerate(context_chunks, start=1):
            metadata = chunk["metadata"]
            header = (
                f"[{position}] 来源：{metadata.get('textbook_title', '未知教材')}"
                f" / {metadata.get('chapter_title', '未知章节')}"
                f"（第 {metadata.get('page_start', 0)} 页）"
            )
            remaining = budget - used_chars
            # 头部之外至少还要留出可用正文空间，否则这个片段放进来也没意义
            if remaining <= len(header) + 20:
                break

            content = truncate_at_boundary(
                str(metadata.get("content", "")), remaining - len(header) - 1
            )
            block = f"{header}\n{content}"
            if used and used_chars + len(block) > budget:
                break
            parts.append(block)
            used.append(chunk)
            used_chars += len(block)

        return "\n\n".join(parts), used

    async def generate_answer(
        self, query: str, context_chunks: List[Dict[str, Any]]
    ) -> QAResponse:
        """基于检索到的上下文生成答案。"""
        context, used_chunks = self._build_context(context_chunks)
        if not used_chunks:
            return QAResponse(answer=NO_ANSWER_TEXT, citations=[], source_chunks=[])

        prompt = (
            "请严格依据下面的参考内容回答用户问题。\n\n"
            f"参考内容：\n{context}\n\n"
            f"用户问题：{query}\n\n"
            "要求：\n"
            "1. 只使用参考内容中的信息，不要引入外部知识；\n"
            "2. 每一条结论后面用方括号标注来源编号，例如 [1]、[2]；\n"
            f"3. 若参考内容确实无法回答该问题，只回复「{NO_ANSWER_TEXT}」；\n"
            "4. 回答准确、简洁、条理清晰。"
        )

        try:
            answer = await call_llm(
                prompt=prompt,
                system_prompt="你是一个严谨的教育知识问答助手，只依据给定教材内容作答。",
            )
        except LLMError as exc:
            logger.error("生成答案失败: %s", exc)
            return QAResponse(
                answer=f"生成答案时出错：{exc}",
                citations=[],
                source_chunks=[],
                retrieved_count=len(context_chunks),
            )

        citations = self._build_citations(used_chunks)
        is_no_answer = self._looks_like_no_answer(answer)

        if is_no_answer:
            return QAResponse(
                answer=answer,
                citations=[],
                source_chunks=[],
                retrieved_count=len(context_chunks),
                top_score=float(used_chunks[0]["similarity"]) if used_chunks else 0.0,
            )

        # 保证「每个回答都带引用」：逐个检查编号引用，缺失的补到末尾
        answer = self._ensure_citations(answer, citations)

        return QAResponse(
            answer=answer,
            citations=citations,
            source_chunks=[c["metadata"].get("content", "") for c in used_chunks],
            retrieved_count=len(context_chunks),
            top_score=float(used_chunks[0]["similarity"]) if used_chunks else 0.0,
        )

    @staticmethod
    def _looks_like_no_answer(answer: str) -> bool:
        """判断回答是否为「知识库中无相关内容」。

        只有短回答才按关键词判定 —— 长回答里顺带出现「无法确定」
        属于正常表述，不应因此丢弃全部引用。
        """
        stripped = answer.strip()
        if not stripped:
            return True
        if NO_ANSWER_TEXT in stripped:
            return True
        if len(stripped) > _NO_ANSWER_MAX_CHARS:
            return False
        return any(marker in stripped for marker in _NO_ANSWER_MARKERS)

    @staticmethod
    def _ensure_citations(answer: str, citations: Sequence[Citation]) -> str:
        """保证回答至少附带一处来源标注。

        模型已经写了编号时**尊重它的选择** —— 强行把未被使用的来源
        补进答案，会把与问题无关的片段也标成"参考来源"。
        只有模型完全没写编号时，才统一追加来源列表。
        """
        if not citations or _CITATION_RE.search(answer):
            return answer

        reference_lines = "\n".join(
            f"[{index}] {citation.textbook} / {citation.chapter}"
            for index, citation in enumerate(citations, start=1)
        )
        return f"{answer}\n\n参考来源：\n{reference_lines}"

    @staticmethod
    def _build_citations(used_chunks: Sequence[Dict[str, Any]]) -> List[Citation]:
        citations: List[Citation] = []
        for chunk in used_chunks:
            metadata = chunk.get("metadata", {})
            citations.append(
                Citation(
                    chunk_id=metadata.get("chunk_id", ""),
                    textbook=metadata.get("textbook_title", ""),
                    chapter=metadata.get("chapter_title", ""),
                    page=metadata.get("page_start", 0),
                    content=str(metadata.get("content", ""))[:200],
                    relevance_score=float(chunk.get("similarity", 0.0)),
                    duplicate_sources=list(chunk.get("also_in", [])),
                )
            )
        return citations

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------
    async def answer_question(self, query: str) -> QAResponse:
        """回答问题。"""
        logger.info("回答问题: %s", query)

        if self.vector_store.size == 0:
            return QAResponse(answer=NO_ANSWER_TEXT, citations=[], source_chunks=[])

        retrieved = await self.retrieve(query)
        if not retrieved:
            return QAResponse(answer=NO_ANSWER_TEXT, citations=[], source_chunks=[])

        response = await self.generate_answer(query, retrieved)
        logger.info(
            "生成答案完成：引用 %d 条，最高相似度 %.3f", len(response.citations), response.top_score
        )
        return response


_qa_instance: Optional[RAGQuestionAnswerer] = None
_qa_lock = threading.Lock()


def get_qa_instance(top_k: Optional[int] = None) -> RAGQuestionAnswerer:
    """获取问答器单例；传入 ``top_k`` 时会更新实例配置。"""
    global _qa_instance
    with _qa_lock:
        if _qa_instance is None:
            _qa_instance = RAGQuestionAnswerer(top_k=top_k)
        elif top_k is not None and _qa_instance.top_k != int(top_k):
            _qa_instance.top_k = int(top_k)
        return _qa_instance


def reset_qa_instance() -> None:
    """重置单例（测试用）。"""
    global _qa_instance
    with _qa_lock:
        _qa_instance = None

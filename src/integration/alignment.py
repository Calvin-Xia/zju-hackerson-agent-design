"""跨教材知识点语义对齐。

流程：

1. **候选召回**：对两组知识点做向量化余弦相似度计算，取相似度 ≥ 阈值的候选对
   （旧实现对每一对做双层 Python 循环，知识点上千时非常慢）；
2. **等价判定**：高于「高置信阈值」的直接判定等价；灰区候选对可选地交给 LLM
   批量复核（一次 Prompt 处理多对，而非一对一次调用）；
3. **一对一匹配**：按相似度从高到低贪心匹配，保证一个知识点最多只与另一本教材的
   一个知识点合并。旧实现允许一个节点同时与多个节点配对，会连锁删除节点、
   造成重复计数。

同名的知识点直接视为等价，无需消耗 LLM 调用。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.embedding.service import get_embedding_service
from src.kg.models import KnowledgeNode
from src.llm.client import LLMError, call_llm_json
from src.shared.config import settings

logger = logging.getLogger(__name__)

# 相似度矩阵分块计算的行数上限，避免超大教材组合爆内存
_MATRIX_ROW_BLOCK = 512
# 单次 LLM 复核的候选对数量
_LLM_VERIFY_BATCH = 10


@dataclass
class AlignedPair:
    """对齐的知识点对"""

    node1_id: str
    node2_id: str
    node1_name: str
    node2_name: str
    similarity_score: float
    is_equivalent: bool
    confidence: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node1_id": self.node1_id,
            "node2_id": self.node2_id,
            "node1_name": self.node1_name,
            "node2_name": self.node2_name,
            "similarity_score": self.similarity_score,
            "is_equivalent": self.is_equivalent,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass
class AlignmentResult:
    """对齐结果"""

    aligned_pairs: List[AlignedPair]
    total_pairs_checked: int
    equivalent_count: int
    avg_similarity: float
    rejected_count: int = 0
    verified_by_llm: int = 0
    textbooks: Tuple[str, str] = ("", "")


@dataclass
class MultiTextbookAlignment:
    """多本教材的全局对齐结果"""

    aligned_pairs: List[AlignedPair]
    pairwise_results: List[AlignmentResult] = field(default_factory=list)
    total_candidates: int = 0
    verified_by_llm: int = 0


def _node_text(node: KnowledgeNode) -> str:
    """用于嵌入的节点文本；包含分类与章节以增强区分度。"""
    parts = [node.name]
    if node.definition:
        parts.append(node.definition)
    if node.category:
        parts.append(node.category)
    return "：".join(parts)


class SemanticAligner:
    """语义对齐器"""

    def __init__(
        self,
        similarity_threshold: Optional[float] = None,
        use_llm_verification: Optional[bool] = None,
        high_confidence_threshold: Optional[float] = None,
    ):
        self.similarity_threshold = (
            settings.ALIGNMENT_THRESHOLD if similarity_threshold is None else similarity_threshold
        )
        self.use_llm_verification = (
            settings.ALIGNMENT_USE_LLM if use_llm_verification is None else use_llm_verification
        )
        self.high_confidence_threshold = (
            settings.ALIGNMENT_HIGH_CONFIDENCE
            if high_confidence_threshold is None
            else high_confidence_threshold
        )
        self.embedding_service = get_embedding_service()

    # ------------------------------------------------------------------
    # 相似度
    # ------------------------------------------------------------------
    def compute_similarity_matrix(
        self, nodes1: List[KnowledgeNode], nodes2: List[KnowledgeNode]
    ) -> np.ndarray:
        """计算两组知识点的余弦相似度矩阵 ``(len(nodes1), len(nodes2))``。"""
        if not nodes1 or not nodes2:
            return np.zeros((len(nodes1), len(nodes2)), dtype=np.float32)

        embeddings1 = np.atleast_2d(self.embedding_service.encode([_node_text(n) for n in nodes1]))
        embeddings2 = np.atleast_2d(self.embedding_service.encode([_node_text(n) for n in nodes2]))
        return np.asarray(self.embedding_service.batch_similarity(embeddings1, embeddings2))

    def _compute_similarity_matrix_blocked(
        self, nodes1: List[KnowledgeNode], nodes2: List[KnowledgeNode]
    ) -> np.ndarray:
        """分块计算相似度矩阵，控制峰值内存。"""
        n, m = len(nodes1), len(nodes2)
        if n == 0 or m == 0:
            return np.zeros((n, m), dtype=np.float32)
        if n * m <= _MATRIX_ROW_BLOCK * m:
            return self.compute_similarity_matrix(nodes1, nodes2)

        embeddings2 = np.atleast_2d(self.embedding_service.encode([_node_text(n) for n in nodes2]))
        matrix = np.zeros((n, m), dtype=np.float32)
        for start in range(0, n, _MATRIX_ROW_BLOCK):
            block = nodes1[start:start + _MATRIX_ROW_BLOCK]
            emb_block = np.atleast_2d(self.embedding_service.encode([_node_text(n) for n in block]))
            matrix[start:start + len(block)] = self.embedding_service.batch_similarity(
                emb_block, embeddings2
            )
        return matrix

    def find_candidate_pairs(
        self,
        nodes1: List[KnowledgeNode],
        nodes2: List[KnowledgeNode],
        threshold: Optional[float] = None,
    ) -> List[Tuple[int, int, float]]:
        """返回相似度达标且按相似度降序排列的候选对 ``[(i, j, sim), ...]``。"""
        if not nodes1 or not nodes2:
            return []

        threshold = self.similarity_threshold if threshold is None else threshold
        similarity_matrix = self._compute_similarity_matrix_blocked(nodes1, nodes2)

        rows, cols = np.nonzero(similarity_matrix >= threshold)
        candidates = [
            (int(i), int(j), float(similarity_matrix[i, j])) for i, j in zip(rows, cols)
        ]
        candidates.sort(key=lambda item: item[2], reverse=True)

        logger.info(
            "候选对 %d 个（阈值 %.2f，规模 %dx%d）",
            len(candidates), threshold, len(nodes1), len(nodes2),
        )
        return candidates

    # ------------------------------------------------------------------
    # 等价判定
    # ------------------------------------------------------------------
    async def verify_equivalence_with_llm(
        self, node1: KnowledgeNode, node2: KnowledgeNode
    ) -> Tuple[bool, float, str]:
        """单对复核（保留接口，内部走批量实现）。"""
        results = await self._verify_pairs_with_llm([(node1, node2)])
        if not results:
            return False, 0.0, "LLM 未返回结果"
        return results[0]

    async def _verify_pairs_with_llm(
        self, pairs: Sequence[Tuple[KnowledgeNode, KnowledgeNode]]
    ) -> List[Tuple[bool, float, str]]:
        """批量复核候选对：一批候选对合并到一次 Prompt 中。"""
        results: List[Tuple[bool, float, str]] = [(False, 0.0, "未复核")] * len(pairs)
        if not pairs:
            return results

        batches = [
            (offset, pairs[offset:offset + _LLM_VERIFY_BATCH])
            for offset in range(0, len(pairs), _LLM_VERIFY_BATCH)
        ]

        async def run_batch(offset: int, batch: Sequence[Tuple[KnowledgeNode, KnowledgeNode]]):
            lines = []
            for idx, (node1, node2) in enumerate(batch):
                lines.append(
                    f"[{idx}] 知识点A：{node1.name} —— {node1.definition[:120]}\n"
                    f"    知识点B：{node2.name} —— {node2.definition[:120]}"
                )
            prompt = (
                "请逐条判断下列知识点对是否描述同一个概念（措辞不同、一方是另一方的"
                "子集/超集都算等价）。\n\n"
                + "\n\n".join(lines)
                + "\n\n请只输出 JSON 数组，元素与输入序号一一对应：\n"
                '[{"index": 0, "is_equivalent": true, "confidence": 0.9, "reason": "理由"}]'
            )
            try:
                data = await call_llm_json(
                    prompt=prompt,
                    system_prompt="你是教育知识专家，擅长判断知识点的等价性。",
                )
            except (LLMError, ValueError) as exc:
                logger.error("LLM 批量复核失败，本批按不等价处理: %s", exc)
                return

            if isinstance(data, dict):
                data = data.get("results") or data.get("pairs") or []
            for item in data if isinstance(data, list) else []:
                try:
                    local_idx = int(item.get("index", -1))
                except (TypeError, ValueError):
                    continue
                if 0 <= local_idx < len(batch):
                    results[offset + local_idx] = (
                        bool(item.get("is_equivalent", False)),
                        float(item.get("confidence", 0.5)),
                        str(item.get("reason", "") or "LLM 判断"),
                    )

        await asyncio.gather(*(run_batch(offset, batch) for offset, batch in batches))
        return results

    # ------------------------------------------------------------------
    # 一对一匹配
    # ------------------------------------------------------------------
    @staticmethod
    def select_one_to_one(
        candidates: Sequence[Tuple[int, int, float]], accepted: Optional[set] = None
    ) -> List[Tuple[int, int, float]]:
        """按相似度降序贪心匹配，保证每个下标最多出现一次。"""
        used_left: set = set()
        used_right: set = set()
        selected: List[Tuple[int, int, float]] = []

        for idx1, idx2, similarity in sorted(candidates, key=lambda item: item[2], reverse=True):
            if accepted is not None and (idx1, idx2) not in accepted:
                continue
            if idx1 in used_left or idx2 in used_right:
                continue
            used_left.add(idx1)
            used_right.add(idx2)
            selected.append((idx1, idx2, similarity))

        return selected

    # ------------------------------------------------------------------
    # 等价判定
    # ------------------------------------------------------------------
    async def _resolve_equivalence(
        self,
        nodes1: List[KnowledgeNode],
        nodes2: List[KnowledgeNode],
        candidates: List[Tuple[int, int, float]],
        llm_budget: Optional[List[int]] = None,
    ) -> Tuple[set, Dict[Tuple[int, int], Tuple[bool, float, str]], int]:
        """把候选对判定为「等价 / 不等价」。

        返回 ``(等价对集合, 判定明细, LLM 实际复核数量)``。
        ``llm_budget`` 是可变容器，用于在多本教材间共享 LLM 复核预算。
        """
        accepted: set = set()
        verdicts: Dict[Tuple[int, int], Tuple[bool, float, str]] = {}
        gray_pairs: List[Tuple[int, int, float]] = []

        for idx1, idx2, similarity in candidates:
            node1, node2 = nodes1[idx1], nodes2[idx2]
            name1, name2 = node1.name.strip(), node2.name.strip()

            if name1 and name1 == name2:
                accepted.add((idx1, idx2))
                verdicts[(idx1, idx2)] = (True, max(similarity, 0.95), "知识点名称完全一致")
                continue

            if similarity >= self.high_confidence_threshold:
                accepted.add((idx1, idx2))
                verdicts[(idx1, idx2)] = (
                    True, similarity, f"嵌入相似度 {similarity:.3f}，达到高置信阈值",
                )
            elif self.use_llm_verification:
                gray_pairs.append((idx1, idx2, similarity))

        verified_by_llm = 0
        if gray_pairs and self.use_llm_verification:
            budget_box = llm_budget if llm_budget is not None else [
                int(settings.ALIGNMENT_LLM_MAX_PAIRS)
            ]
            if budget_box[0] <= 0:
                logger.info("LLM 复核预算已用尽，%d 个灰区候选对按不等价处理", len(gray_pairs))
                gray_pairs = []
            elif len(gray_pairs) > budget_box[0]:
                logger.info(
                    "灰区候选对 %d 个，超出剩余预算 %d，按相似度保留前 %d 个",
                    len(gray_pairs), budget_box[0], budget_box[0],
                )
                gray_pairs = gray_pairs[: budget_box[0]]

            if gray_pairs:
                verdict_list = await self._verify_pairs_with_llm(
                    [(nodes1[i], nodes2[j]) for i, j, _ in gray_pairs]
                )
                budget_box[0] -= len(gray_pairs)
                for (idx1, idx2, similarity), verdict in zip(gray_pairs, verdict_list):
                    is_equivalent, confidence, reason = verdict
                    verdicts[(idx1, idx2)] = (is_equivalent, confidence, reason)
                    verified_by_llm += 1
                    if is_equivalent:
                        accepted.add((idx1, idx2))

        return accepted, verdicts, verified_by_llm

    @staticmethod
    def _build_pairs(
        nodes1: List[KnowledgeNode],
        nodes2: List[KnowledgeNode],
        selected: Sequence[Tuple[int, int, float]],
        verdicts: Dict[Tuple[int, int], Tuple[bool, float, str]],
    ) -> List[AlignedPair]:
        pairs: List[AlignedPair] = []
        for idx1, idx2, similarity in selected:
            node1, node2 = nodes1[idx1], nodes2[idx2]
            _flag, confidence, reason = verdicts.get(
                (idx1, idx2), (True, similarity, f"嵌入相似度 {similarity:.3f}")
            )
            pairs.append(
                AlignedPair(
                    node1_id=node1.id,
                    node2_id=node2.id,
                    node1_name=node1.name,
                    node2_name=node2.name,
                    similarity_score=similarity,
                    is_equivalent=True,
                    confidence=min(1.0, max(0.0, float(confidence))),
                    reason=reason,
                )
            )
        return pairs

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    async def align_nodes(
        self,
        nodes1: List[KnowledgeNode],
        nodes2: List[KnowledgeNode],
        textbook1_id: str = "",
        textbook2_id: str = "",
    ) -> AlignmentResult:
        """对齐两组知识点，返回一对一匹配后的等价对。"""
        candidates = await asyncio.to_thread(self.find_candidate_pairs, nodes1, nodes2)
        if not candidates:
            return AlignmentResult(
                aligned_pairs=[],
                total_pairs_checked=0,
                equivalent_count=0,
                avg_similarity=0.0,
                textbooks=(textbook1_id, textbook2_id),
            )

        accepted, verdicts, verified_by_llm = await self._resolve_equivalence(
            nodes1, nodes2, candidates
        )
        selected = self.select_one_to_one(candidates, accepted)
        aligned_pairs = self._build_pairs(nodes1, nodes2, selected, verdicts)

        avg_similarity = (
            float(np.mean([p.similarity_score for p in aligned_pairs])) if aligned_pairs else 0.0
        )
        logger.info(
            "对齐完成: %d/%d 候选对判定等价（一对一匹配）",
            len(aligned_pairs), len(candidates),
        )

        return AlignmentResult(
            aligned_pairs=aligned_pairs,
            total_pairs_checked=len(candidates),
            equivalent_count=len(aligned_pairs),
            avg_similarity=avg_similarity,
            rejected_count=len(candidates) - len(aligned_pairs),
            verified_by_llm=verified_by_llm,
            textbooks=(textbook1_id, textbook2_id),
        )

    async def align_textbooks(
        self, textbook_nodes: Dict[str, List[KnowledgeNode]]
    ) -> "MultiTextbookAlignment":
        """跨全部教材的全局一对一对齐。

        与 ``align_multiple_textbooks`` 的区别：这里只在**全局**层面做一次
        一对一匹配，因此同一个知识点不会在一组教材里保留、又在另一组里被删除。
        """
        textbook_ids = list(textbook_nodes.keys())
        llm_budget = [int(settings.ALIGNMENT_LLM_MAX_PAIRS)]
        total_candidates = 0
        total_verified = 0
        pairwise_results: List[AlignmentResult] = []

        # (similarity, textbook1, textbook2, node1_id, node2_id, confidence, reason)
        global_candidates: List[Tuple[float, str, str, str, str, float, str]] = []

        for i in range(len(textbook_ids)):
            for j in range(i + 1, len(textbook_ids)):
                id1, id2 = textbook_ids[i], textbook_ids[j]
                nodes1, nodes2 = textbook_nodes[id1], textbook_nodes[id2]
                candidates = await asyncio.to_thread(
                    self.find_candidate_pairs, nodes1, nodes2
                )
                total_candidates += len(candidates)
                if not candidates:
                    continue

                logger.info("对齐教材: %s vs %s（%d 个候选对）", id1, id2, len(candidates))
                accepted, verdicts, verified = await self._resolve_equivalence(
                    nodes1, nodes2, candidates, llm_budget=llm_budget
                )
                total_verified += verified

                pair_selected = self.select_one_to_one(candidates, accepted)
                for idx1, idx2, similarity in pair_selected:
                    _flag, confidence, reason = verdicts.get(
                        (idx1, idx2), (True, similarity, f"嵌入相似度 {similarity:.3f}")
                    )
                    global_candidates.append(
                        (similarity, id1, id2, nodes1[idx1].id, nodes2[idx2].id,
                         confidence, reason)
                    )

                pairwise_results.append(
                    AlignmentResult(
                        aligned_pairs=self._build_pairs(nodes1, nodes2, pair_selected, verdicts),
                        total_pairs_checked=len(candidates),
                        equivalent_count=len(pair_selected),
                        avg_similarity=(
                            float(np.mean([s for _, _, s in pair_selected]))
                            if pair_selected else 0.0
                        ),
                        rejected_count=len(candidates) - len(pair_selected),
                        verified_by_llm=verified,
                        textbooks=(id1, id2),
                    )
                )

        # 全局一对一匹配
        used: set = set()
        node_lookup: Dict[str, KnowledgeNode] = {}
        for nodes in textbook_nodes.values():
            for node in nodes:
                node_lookup[node.id] = node

        aligned_pairs: List[AlignedPair] = []
        for similarity, _id1, _id2, node1_id, node2_id, confidence, reason in sorted(
            global_candidates, key=lambda item: item[0], reverse=True
        ):
            if node1_id in used or node2_id in used:
                continue
            used.add(node1_id)
            used.add(node2_id)
            node1, node2 = node_lookup[node1_id], node_lookup[node2_id]
            aligned_pairs.append(
                AlignedPair(
                    node1_id=node1_id,
                    node2_id=node2_id,
                    node1_name=node1.name,
                    node2_name=node2.name,
                    similarity_score=similarity,
                    is_equivalent=True,
                    confidence=min(1.0, max(0.0, float(confidence))),
                    reason=reason,
                )
            )

        logger.info(
            "全局对齐完成: 候选 %d 对 -> 等价 %d 对（LLM 复核 %d 对）",
            total_candidates, len(aligned_pairs), total_verified,
        )
        return MultiTextbookAlignment(
            aligned_pairs=aligned_pairs,
            pairwise_results=pairwise_results,
            total_candidates=total_candidates,
            verified_by_llm=total_verified,
        )

    async def align_multiple_textbooks(
        self, textbook_nodes: Dict[str, List[KnowledgeNode]]
    ) -> List[AlignmentResult]:
        """对齐多本教材的知识点（两两组合，各自独立一对一匹配）。"""
        textbook_ids = list(textbook_nodes.keys())
        results: List[AlignmentResult] = []

        for i in range(len(textbook_ids)):
            for j in range(i + 1, len(textbook_ids)):
                id1, id2 = textbook_ids[i], textbook_ids[j]
                logger.info("对齐教材: %s vs %s", id1, id2)
                results.append(
                    await self.align_nodes(
                        textbook_nodes[id1], textbook_nodes[id2],
                        textbook1_id=id1, textbook2_id=id2,
                    )
                )

        return results


async def align_knowledge_nodes(
    nodes1: List[KnowledgeNode],
    nodes2: List[KnowledgeNode],
    similarity_threshold: float = 0.8,
    use_llm: bool = True,
) -> AlignmentResult:
    """便捷函数：对齐两组知识点。"""
    aligner = SemanticAligner(
        similarity_threshold=similarity_threshold,
        use_llm_verification=use_llm,
    )
    return await aligner.align_nodes(nodes1, nodes2)

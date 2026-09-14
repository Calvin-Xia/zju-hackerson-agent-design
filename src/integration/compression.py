"""压缩比控制。

需求定义：``压缩比 = 整合后字数 / 原始总字数``，要求 ≤ 30%。

旧实现只提供了 ``optimize_compression``，但**从未在整合流程里被调用**，
且其内部用 ``break`` 提前退出（遇到第一个放不下的节点就停止），
所以实际压缩比既不达标也不可控。

本模块提供三级递进的压缩策略：

1. **合并**（在决策阶段完成）—— 去重同一概念，描述取并集；
2. **摘要**—— 按节点重要度分配字数预算，对描述做抽取式摘要（保留全部知识点）；
3. **筛选**—— 若仍超预算，按重要度从低到高丢弃节点，只保留高价值知识点。

第 2 步是达成 30% 目标的主力：它保住了知识点的完整结构，
而不是简单粗暴地砍掉大半内容。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.kg.models import KnowledgeNode, KnowledgeRelation
from src.shared.config import settings
from src.shared.text import extractive_condense

logger = logging.getLogger(__name__)


def node_char_count(node: KnowledgeNode) -> int:
    """单个知识点的字数（名称 + 定义）。"""
    return len(node.name or "") + len(node.definition or "")


@dataclass
class CompressionStats:
    """压缩统计"""

    original_node_count: int
    original_relation_count: int
    original_total_chars: int
    compressed_node_count: int
    compressed_relation_count: int
    compressed_total_chars: int
    compression_ratio: float
    is_within_limit: bool
    condensed_node_count: int = 0
    dropped_node_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_node_count": self.original_node_count,
            "original_relation_count": self.original_relation_count,
            "original_total_chars": self.original_total_chars,
            "compressed_node_count": self.compressed_node_count,
            "compressed_relation_count": self.compressed_relation_count,
            "compressed_total_chars": self.compressed_total_chars,
            "compression_ratio": self.compression_ratio,
            "is_within_limit": self.is_within_limit,
            "condensed_node_count": self.condensed_node_count,
            "dropped_node_count": self.dropped_node_count,
        }


class CompressionController:
    """压缩比控制器"""

    def __init__(
        self,
        max_compression_ratio: Optional[float] = None,
        enable_condense: Optional[bool] = None,
    ):
        self.max_compression_ratio = (
            settings.MAX_COMPRESSION_RATIO
            if max_compression_ratio is None
            else max_compression_ratio
        )
        self.enable_condense = (
            settings.COMPRESSION_CONDENSE if enable_condense is None else enable_condense
        )

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def count_chars(self, nodes: Sequence[KnowledgeNode]) -> int:
        return sum(node_char_count(node) for node in nodes)

    def compute_compression_stats(
        self,
        original_nodes: List[KnowledgeNode],
        original_relations: List[KnowledgeRelation],
        compressed_nodes: List[KnowledgeNode],
        compressed_relations: List[KnowledgeRelation],
        condensed_node_count: int = 0,
        dropped_node_count: int = 0,
    ) -> CompressionStats:
        original_chars = self.count_chars(original_nodes)
        compressed_chars = self.count_chars(compressed_nodes)
        ratio = (compressed_chars / original_chars) if original_chars else 0.0

        return CompressionStats(
            original_node_count=len(original_nodes),
            original_relation_count=len(original_relations),
            original_total_chars=original_chars,
            compressed_node_count=len(compressed_nodes),
            compressed_relation_count=len(compressed_relations),
            compressed_total_chars=compressed_chars,
            compression_ratio=ratio,
            is_within_limit=ratio <= self.max_compression_ratio,
            condensed_node_count=condensed_node_count,
            dropped_node_count=dropped_node_count,
        )

    # ------------------------------------------------------------------
    # 节点重要度
    # ------------------------------------------------------------------
    @staticmethod
    def score_nodes(
        nodes: Sequence[KnowledgeNode], relations: Sequence[KnowledgeRelation]
    ) -> Dict[str, float]:
        """重要度打分：出现频次 + 图度数 + 描述信息量。"""
        degree: Dict[str, int] = {}
        for relation in relations:
            degree[relation.source] = degree.get(relation.source, 0) + 1
            degree[relation.target] = degree.get(relation.target, 0) + 1

        scores: Dict[str, float] = {}
        for node in nodes:
            frequency = max(1, int(node.frequency or 1))
            # 归一化到 [0,1]，避免长描述单方面主导排序
            richness = min(len(node.definition or ""), 200) / 200.0
            degree_score = min(degree.get(node.id, 0), 10) / 10.0
            scores[node.id] = 2.0 * (frequency - 1) + 1.5 * degree_score + 1.0 * richness
        return scores

    # ------------------------------------------------------------------
    # 旧接口（保留兼容）
    # ------------------------------------------------------------------
    def select_nodes_for_compression(
        self, nodes: List[KnowledgeNode], target_chars: int
    ) -> List[KnowledgeNode]:
        """按重要度选取节点，使总字数不超过 ``target_chars``。

        旧实现遇到放不下的节点就 ``break``，会漏掉后面更小的节点；
        这里改为 ``continue``，用贪心填充预算。
        """
        scores = self.score_nodes(nodes, [])
        ordered = sorted(
            nodes,
            key=lambda n: (scores.get(n.id, 0.0), node_char_count(n)),
            reverse=True,
        )

        selected: List[KnowledgeNode] = []
        used = 0
        for node in ordered:
            size = node_char_count(node)
            if used + size <= target_chars:
                selected.append(node)
                used += size

        # 保持原有顺序，便于前端展示与阅读
        order = {node.id: index for index, node in enumerate(nodes)}
        selected.sort(key=lambda n: order.get(n.id, 0))
        logger.info("按预算选取 %d/%d 个节点，占用 %d/%d 字",
                    len(selected), len(nodes), used, target_chars)
        return selected

    def optimize_compression(
        self,
        nodes: List[KnowledgeNode],
        relations: List[KnowledgeRelation],
    ) -> Tuple[List[KnowledgeNode], List[KnowledgeRelation]]:
        """兼容旧接口的压缩（仅做节点筛选，不做摘要）。"""
        original_chars = self.count_chars(nodes)
        target_chars = int(original_chars * self.max_compression_ratio)
        if original_chars <= target_chars:
            return nodes, relations

        selected = self.select_nodes_for_compression(nodes, target_chars)
        selected_ids = {node.id for node in selected}
        selected_relations = [
            rel for rel in relations if rel.source in selected_ids and rel.target in selected_ids
        ]
        logger.info("压缩优化: %d -> %d 节点, %d -> %d 关系",
                    len(nodes), len(selected), len(relations), len(selected_relations))
        return selected, selected_relations

    # ------------------------------------------------------------------
    # 达标压缩
    # ------------------------------------------------------------------
    def enforce_ratio(
        self,
        nodes: List[KnowledgeNode],
        relations: List[KnowledgeRelation],
        original_total_chars: Optional[int] = None,
        protected_ids: Optional[Set[str]] = None,
    ) -> Tuple[List[KnowledgeNode], List[KnowledgeRelation], CompressionStats]:
        """把内容压缩到目标比例以内，返回压缩后的节点、关系与统计。

        ``original_total_chars`` 用于在「已合并」的节点集合上继续按原始字数计算比例。
        """
        original_chars = (
            original_total_chars if original_total_chars is not None
            else self.count_chars(nodes)
        )
        original_node_count = len(nodes)
        target_chars = int(original_chars * self.max_compression_ratio)

        current_chars = self.count_chars(nodes)
        condensed_count = 0
        dropped_count = 0

        if original_chars == 0:
            stats = self.compute_compression_stats(nodes, relations, nodes, relations)
            return nodes, relations, stats

        # 第 1 级：抽取式摘要（保留全部知识点，缩短描述）
        if current_chars > target_chars and self.enable_condense:
            nodes, condensed_count = self._condense_nodes(nodes, target_chars, protected_ids)
            current_chars = self.count_chars(nodes)
            logger.info("摘要压缩后字数: %d -> %d（目标 %d）", original_chars, current_chars, target_chars)

        # 第 2 级：筛选知识点（丢弃重要度最低的节点）
        if current_chars > target_chars:
            nodes, dropped_count = self._drop_lowest_value_nodes(
                nodes, relations, target_chars, protected_ids
            )

        retained_ids = {node.id for node in nodes}
        retained_relations = [
            rel for rel in relations if rel.source in retained_ids and rel.target in retained_ids
        ]

        compressed_chars = self.count_chars(nodes)
        ratio = compressed_chars / original_chars if original_chars else 0.0
        stats = CompressionStats(
            original_node_count=original_node_count,
            original_relation_count=len(relations),
            original_total_chars=original_chars,
            compressed_node_count=len(nodes),
            compressed_relation_count=len(retained_relations),
            compressed_total_chars=compressed_chars,
            compression_ratio=ratio,
            is_within_limit=ratio <= self.max_compression_ratio,
            condensed_node_count=condensed_count,
            dropped_node_count=dropped_count,
        )

        logger.info(
            "压缩完成: %d -> %d 字，压缩比 %.2f%%（上限 %.2f%%），摘要 %d 个，丢弃 %d 个",
            original_chars, stats.compressed_total_chars,
            stats.compression_ratio * 100, self.max_compression_ratio * 100,
            condensed_count, dropped_count,
        )
        return nodes, retained_relations, stats

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _condense_nodes(
        self,
        nodes: List[KnowledgeNode],
        target_chars: int,
        protected_ids: Optional[Set[str]],
    ) -> Tuple[List[KnowledgeNode], int]:
        """按重要度为每个节点分配字数预算并做抽取式摘要。

        已经很精炼的描述（短于 ``COMPRESSION_MIN_KEEP_CHARS``）不做摘要 ——
        对一句话做抽取只会截断成病句，这类节点交给「丢弃低价值节点」环节处理。
        """
        min_definition = max(0, int(settings.COMPRESSION_MIN_DEFINITION_CHARS))
        min_keep = max(min_definition, int(settings.COMPRESSION_MIN_KEEP_CHARS))
        protected_ids = protected_ids or set()

        scores = self.score_nodes(nodes, [])
        weighted_nodes = [(node, max(scores.get(node.id, 0.0), 0.05)) for node in nodes]
        total_weight = sum(weight for _, weight in weighted_nodes) or 1.0

        condensed_nodes: List[KnowledgeNode] = []
        condensed_count = 0

        for node, weight in weighted_nodes:
            definition = node.definition or ""
            if len(definition) <= min_keep:
                condensed_nodes.append(node)
                continue

            budget = int(target_chars * (weight / total_weight))
            allowed = max(min_keep, budget - len(node.name or ""))
            if len(definition) <= allowed:
                condensed_nodes.append(node)
                continue

            new_definition = extractive_condense(definition, allowed)
            # 摘要若丢失过多内容（不足原文一半），保守地按比例多保留一些
            if len(new_definition) < max(min_keep, len(definition) // 2):
                new_definition = extractive_condense(
                    definition, max(min_keep, len(definition) // 2)
                )
            if new_definition != definition:
                condensed_count += 1
            condensed_nodes.append(node.model_copy(update={"definition": new_definition}))

        # 摘要后仍超目标时，按比例再收紧一轮（受保护与已精炼的节点跳过）
        current = self.count_chars(condensed_nodes)
        if current > target_chars:
            ratio = target_chars / current
            tightened: List[KnowledgeNode] = []
            for node in condensed_nodes:
                definition = node.definition or ""
                if node.id in protected_ids or len(definition) <= min_keep:
                    tightened.append(node)
                    continue
                new_definition = extractive_condense(
                    definition, max(min_keep, int(len(definition) * ratio))
                )
                if new_definition != definition:
                    condensed_count += 1
                tightened.append(node.model_copy(update={"definition": new_definition}))
            condensed_nodes = tightened
            current = self.count_chars(condensed_nodes)

        return condensed_nodes, condensed_count

    def _drop_lowest_value_nodes(
        self,
        nodes: List[KnowledgeNode],
        relations: List[KnowledgeRelation],
        target_chars: int,
        protected_ids: Optional[Set[str]],
    ) -> Tuple[List[KnowledgeNode], int]:
        """按重要度从低到高丢弃节点，直到满足预算。

        始终至少保留一个节点：整合结果为空白知识图谱是没有意义的，
        这种情况下宁可略微超出压缩比，也不把内容清空。
        """
        scores = self.score_nodes(nodes, relations)
        protected_ids = protected_ids or set()

        droppable = [n for n in nodes if n.id not in protected_ids]
        droppable.sort(key=lambda n: scores.get(n.id, 0.0))

        current = self.count_chars(nodes)
        dropped: set = set()
        for node in droppable:
            if current <= target_chars or len(dropped) >= len(nodes) - 1:
                break
            dropped.add(node.id)
            current -= node_char_count(node)

        if current > target_chars:
            logger.warning(
                "压缩后仍超过目标（%d > %d）：已保留受保护知识点与至少一个节点，无法继续压缩",
                current, target_chars,
            )

        return [n for n in nodes if n.id not in dropped], len(dropped)


def compute_compression_ratio(
    original_nodes: List[KnowledgeNode], compressed_nodes: List[KnowledgeNode]
) -> float:
    """便捷函数：计算压缩比 ``(0-1)``。"""
    controller = CompressionController()
    original_chars = controller.count_chars(original_nodes)
    if original_chars == 0:
        return 0.0
    return controller.count_chars(compressed_nodes) / original_chars

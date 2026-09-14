"""跨教材整合流水线。

把「语义对齐 → 整合决策 → 决策应用 → 压缩比控制」串成一条可测试的流水线，
API 路由只负责调度与状态上报。

关键点：压缩比控制（``≤ 30%``）是赛题硬性要求，旧实现里
``CompressionController`` 从未被调用，因此这里显式作为流水线的最后一步。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from src.integration.alignment import MultiTextbookAlignment, SemanticAligner
from src.integration.compression import CompressionController, CompressionStats
from src.integration.decision import (
    ApplyStats,
    DecisionMaker,
    DecisionResult,
    IntegrationDecision,
    apply_decisions,
)
from src.kg.models import KnowledgeGraph, KnowledgeNode, KnowledgeRelation
from src.shared.config import settings

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[float, str], None]]


@dataclass
class IntegrationOutcome:
    """整合结果"""

    textbook_ids: List[str]
    decisions: List[IntegrationDecision]
    decision_result: DecisionResult
    nodes: List[KnowledgeNode]
    relations: List[KnowledgeRelation]
    stats: CompressionStats
    alignment: MultiTextbookAlignment
    apply_stats: ApplyStats
    original_node_count: int
    original_relation_count: int
    original_total_chars: int

    def statistics(self) -> Dict[str, Any]:
        return {
            "original_textbook_count": len(self.textbook_ids),
            "total_original_chars": self.stats.original_total_chars,
            "total_compressed_chars": self.stats.compressed_total_chars,
            "compression_ratio": self.stats.compression_ratio,
            "is_within_limit": self.stats.is_within_limit,
            "max_compression_ratio": settings.MAX_COMPRESSION_RATIO,
            "total_decisions": self.decision_result.total_decisions,
            "merge_count": self.decision_result.merge_count,
            "keep_count": self.decision_result.keep_count,
            "remove_count": self.decision_result.remove_count,
            "original_node_count": self.original_node_count,
            "compressed_node_count": self.stats.compressed_node_count,
            "original_relation_count": self.original_relation_count,
            "compressed_relation_count": self.stats.compressed_relation_count,
            "condensed_node_count": self.stats.condensed_node_count,
            "dropped_node_count": self.stats.dropped_node_count,
            "alignment_candidates": self.alignment.total_candidates,
            "aligned_pair_count": len(self.alignment.aligned_pairs),
        }


def collect_nodes(graphs: Dict[str, KnowledgeGraph]) -> Tuple[List[KnowledgeNode], List[KnowledgeRelation]]:
    """汇总所有教材的节点与关系（保持去重后的顺序）。"""
    nodes: List[KnowledgeNode] = []
    relations: List[KnowledgeRelation] = []
    seen_nodes: Set[str] = set()
    seen_relations: Set[Tuple[str, str, str]] = set()

    for graph in graphs.values():
        for node in graph.nodes:
            if node.id in seen_nodes:
                continue
            seen_nodes.add(node.id)
            nodes.append(node)
        for relation in graph.relations:
            key = (relation.source, relation.target, relation.relation_type)
            if key in seen_relations:
                continue
            seen_relations.add(key)
            relations.append(relation)

    return nodes, relations


async def run_integration(
    graphs: Dict[str, KnowledgeGraph],
    progress_cb: ProgressCallback = None,
) -> IntegrationOutcome:
    """执行完整的跨教材整合流程。"""

    def report(progress: float, message: str) -> None:
        if progress_cb:
            try:
                progress_cb(progress, message)
            except Exception as exc:  # 进度上报不应影响主流程
                logger.warning("进度回调失败: %s", exc)

    if not graphs:
        raise ValueError("没有可用的知识图谱")

    report(5.0, "汇总知识点")
    all_nodes, original_relations = collect_nodes(graphs)
    if not all_nodes:
        raise ValueError("教材中没有可用于整合的知识点")

    textbook_nodes = {file_id: list(graph.nodes) for file_id, graph in graphs.items()}
    nodes_map: Dict[str, KnowledgeNode] = {node.id: node for node in all_nodes}

    report(15.0, "语义对齐")
    aligner = SemanticAligner()
    alignment = await aligner.align_textbooks(textbook_nodes)

    report(45.0, "生成整合决策")
    maker = DecisionMaker(use_llm_reason=False)
    decision_result = await maker.make_decisions_for_aligned_pairs(
        alignment.aligned_pairs, nodes_map
    )

    report(65.0, "应用整合决策")
    merged_nodes, merged_relations, apply_stats = apply_decisions(
        all_nodes, original_relations, decision_result.decisions
    )

    report(80.0, "控制压缩比")
    original_total_chars = sum(
        len(node.name or "") + len(node.definition or "") for node in all_nodes
    )
    controller = CompressionController()
    # 跨教材共享的核心概念（整合后频次 >= 2）优先保留完整描述
    protected_ids = {
        node.id for node in merged_nodes
        if (node.frequency or 1) >= 2
    }
    final_nodes, final_relations, stats = controller.enforce_ratio(
        merged_nodes,
        merged_relations,
        original_total_chars=original_total_chars,
        protected_ids=protected_ids,
    )

    report(95.0, "整合完成")
    return IntegrationOutcome(
        textbook_ids=list(graphs.keys()),
        decisions=decision_result.decisions,
        decision_result=decision_result,
        nodes=final_nodes,
        relations=final_relations,
        stats=stats,
        alignment=alignment,
        apply_stats=apply_stats,
        original_node_count=len(all_nodes),
        original_relation_count=len(original_relations),
        original_total_chars=original_total_chars,
    )

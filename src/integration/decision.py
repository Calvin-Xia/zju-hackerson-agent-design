"""整合决策机制。

三种决策动作的语义（旧实现中 ``keep`` 在前端流程里不生效、``remove`` 永远不可达）：

* ``merge``  —— 描述同一概念，且两方都有独有信息：合并描述，保留信息量最大的一侧；
* ``keep``   —— 描述同一概念但相似度中等：保留信息更完整的一侧，避免引入矛盾表述；
* ``remove`` —— 候选节点没有独有信息（定义已被完全覆盖）：直接删除。

默认走**规则判定**，不调用 LLM，因此整本整合流程是确定性的、秒级完成；
仅在显式开启 ``use_llm_reason`` 时才对决策理由做 LLM 润色。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.kg.models import KnowledgeNode, KnowledgeRelation
from src.llm.client import LLMError, call_llm, extract_json
from src.shared.config import settings
from src.shared.text import contains_text, merge_definitions

logger = logging.getLogger(__name__)


class DecisionAction(str, Enum):
    """决策动作类型"""

    MERGE = "merge"    # 合并重复（描述取并集）
    KEEP = "keep"      # 保留更完整的一侧
    REMOVE = "remove"  # 删除冗余（无独有信息）


@dataclass
class IntegrationDecision:
    """整合决策"""

    decision_id: str
    action: DecisionAction
    affected_nodes: List[str]
    result_node: Optional[str]
    reason: str
    confidence: float
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "action": self.action.value,
            "affected_nodes": self.affected_nodes,
            "result_node": self.result_node,
            "reason": self.reason,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class DecisionResult:
    """决策结果"""

    decisions: List[IntegrationDecision]
    total_decisions: int
    merge_count: int
    keep_count: int
    remove_count: int


@dataclass
class ApplyStats:
    """决策应用后的统计"""

    merged_nodes: int = 0
    kept_nodes: int = 0
    removed_nodes: int = 0
    enriched_nodes: int = 0


@dataclass
class _Candidate:
    """内部使用的候选节点信息"""

    node: KnowledgeNode
    has_unique_content: bool
    richness: int


def _richness(node: KnowledgeNode) -> int:
    """节点信息量：描述长度为主，频次与关系度加权。"""
    return len(node.definition or "") + 10 * len(node.name or "")


def _has_unique_content(target: str, other: str) -> bool:
    """``target`` 是否含有 ``other`` 未覆盖的信息。"""
    if not target:
        return False
    if not other:
        return True
    return not contains_text(other, target)


def make_rule_based_reason(
    action: DecisionAction, node1: KnowledgeNode, node2: KnowledgeNode, similarity: float
) -> str:
    """生成可解释的规则化理由。

    知识点同名时要单独措辞 —— 「「静脉」与「静脉」」这种表述读起来像 bug，
    而跨教材整合中同名知识点恰恰是最常见的情况。
    """
    same_name = node1.name.strip() == node2.name.strip() and bool(node1.name.strip())

    if action == DecisionAction.MERGE:
        if same_name:
            return (
                f"知识点「{node1.name}」在两本教材中均有出现，且各自包含独有表述"
                f"（相似度 {similarity:.2f}），已合并描述并保留信息量更大的一侧。"
            )
        return (
            f"「{node1.name}」与「{node2.name}」描述同一概念"
            f"（相似度 {similarity:.2f}），且各自包含独有表述，已合并描述并保留信息量更大的一侧。"
        )

    if action == DecisionAction.KEEP:
        richer, poorer = (
            (node1, node2) if _richness(node1) >= _richness(node2) else (node2, node1)
        )
        if same_name:
            return (
                f"知识点「{node1.name}」在两本教材中重复出现（相似度 {similarity:.2f}），"
                f"保留描述更完整的一侧，合并重复表述。"
            )
        return (
            f"「{node1.name}」与「{node2.name}」判定为同一概念"
            f"（相似度 {similarity:.2f}），保留描述更完整的「{richer.name}」，"
            f"合并「{poorer.name}」的重复表述。"
        )

    # REMOVE：描述已被完全覆盖，删除无损
    if same_name:
        return (
            f"知识点「{node1.name}」在两本教材中重复出现，且描述无额外信息"
            f"（相似度 {similarity:.2f}），删除重复项。"
        )
    return (
        f"「{node2.name}」的描述已被「{node1.name}」完全覆盖"
        f"（相似度 {similarity:.2f}），删除以避免重复。"
    )


class DecisionMaker:
    """决策生成器"""

    def __init__(self, use_llm_reason: bool = False, max_llm_reasons: int = 20):
        self.use_llm_reason = use_llm_reason
        self.max_llm_reasons = max(0, int(max_llm_reasons))

    # ------------------------------------------------------------------
    # LLM 理由（可选，保留原接口）
    # ------------------------------------------------------------------
    async def generate_decision_reason(
        self, action: DecisionAction, nodes: List[KnowledgeNode]
    ) -> Tuple[str, float]:
        """使用 LLM 生成决策理由。"""
        nodes_info = "\n".join(
            f"- {node.name}: {node.definition[:50]}…" if len(node.definition) > 50
            else f"- {node.name}: {node.definition}"
            for node in nodes
        )

        action_hint = {
            DecisionAction.MERGE: "以下知识点描述的是同一个概念，请给出合并的理由",
            DecisionAction.KEEP: "以下知识点中需要保留信息最完整的一版，请给出保留理由",
            DecisionAction.REMOVE: "以下知识点存在冗余，请给出删除理由",
        }[action]

        prompt = (
            f"{action_hint}：\n\n{nodes_info}\n\n"
            '请以 JSON 格式返回：\n{"reason": "判断理由", "confidence": 0.0-1.0}'
        )

        try:
            response = await call_llm(
                prompt=prompt,
                system_prompt="你是一个教育知识整合专家，擅长判断知识点的整合策略。",
            )
            data = extract_json(response)
            if isinstance(data, dict):
                return (
                    str(data.get("reason", "无理由")),
                    float(data.get("confidence", 0.5) or 0.5),
                )
        except (LLMError, ValueError, TypeError) as exc:
            logger.error("生成决策理由失败: %s", exc)
        return make_rule_based_reason(action, nodes[0], nodes[-1], 0.0), 0.5

    # ------------------------------------------------------------------
    # 决策生成
    # ------------------------------------------------------------------
    def _classify(
        self, node1: KnowledgeNode, node2: KnowledgeNode, similarity: float
    ) -> Tuple[DecisionAction, KnowledgeNode, KnowledgeNode]:
        """判定动作，并返回 (动作, 保留侧, 被合并侧)。"""
        richer, poorer = (
            (node1, node2) if _richness(node1) >= _richness(node2) else (node2, node1)
        )

        poorer_unique = _has_unique_content(poorer.definition, richer.definition)
        if not poorer_unique:
            # 候选描述已被完全覆盖，删除即无损
            return DecisionAction.REMOVE, richer, poorer

        if similarity >= self.similarity_for_merge:
            return DecisionAction.MERGE, richer, poorer

        return DecisionAction.KEEP, richer, poorer

    @property
    def similarity_for_merge(self) -> float:
        return float(settings.ALIGNMENT_HIGH_CONFIDENCE)

    async def make_decisions_for_aligned_pairs(
        self,
        aligned_pairs: Iterable[Any],
        nodes_map: Dict[str, KnowledgeNode],
    ) -> DecisionResult:
        """为对齐的知识点对生成整合决策。"""
        decisions: List[IntegrationDecision] = []
        llm_budget = self.max_llm_reasons if self.use_llm_reason else 0

        for pair in aligned_pairs:
            node1 = nodes_map.get(pair.node1_id)
            node2 = nodes_map.get(pair.node2_id)
            if not node1 or not node2:
                continue

            similarity = float(getattr(pair, "similarity_score", 0.0) or 0.0)
            action, keeper, merged = self._classify(node1, node2, similarity)

            if action == DecisionAction.REMOVE:
                affected_nodes = [merged.id]
                result_node: Optional[str] = keeper.id
            else:
                affected_nodes = [keeper.id, merged.id]
                result_node = keeper.id

            if llm_budget > 0:
                reason, confidence = await self.generate_decision_reason(
                    action, [node1, node2]
                )
                llm_budget -= 1
            else:
                reason = make_rule_based_reason(action, node1, node2, similarity)
                confidence = min(1.0, max(similarity, float(getattr(pair, "confidence", 0.0) or 0.0)))

            decisions.append(
                IntegrationDecision(
                    decision_id=f"decision_{uuid.uuid4().hex[:8]}",
                    action=action,
                    affected_nodes=affected_nodes,
                    result_node=result_node,
                    reason=reason,
                    confidence=confidence,
                )
            )

        merge_count = sum(1 for d in decisions if d.action == DecisionAction.MERGE)
        keep_count = sum(1 for d in decisions if d.action == DecisionAction.KEEP)
        remove_count = sum(1 for d in decisions if d.action == DecisionAction.REMOVE)

        logger.info(
            "生成 %d 条决策: merge=%d, keep=%d, remove=%d",
            len(decisions), merge_count, keep_count, remove_count,
        )

        return DecisionResult(
            decisions=decisions,
            total_decisions=len(decisions),
            merge_count=merge_count,
            keep_count=keep_count,
            remove_count=remove_count,
        )


# ----------------------------------------------------------------------
# 决策应用
# ----------------------------------------------------------------------
def apply_decisions(
    nodes: List[KnowledgeNode],
    relations: List[KnowledgeRelation],
    decisions: Iterable[IntegrationDecision],
) -> Tuple[List[KnowledgeNode], List[KnowledgeRelation], ApplyStats]:
    """把决策应用到知识点与关系上。

    * ``merge``  合并描述（并集去重），保留 ``result_node``；
    * ``keep``   保留 ``result_node`` 原有描述，丢弃重复节点；
    * ``remove`` 删除指定节点。

    被删除节点挂在关系会被同步清理，避免出现悬空边。
    """
    node_by_id: Dict[str, KnowledgeNode] = {n.id: n for n in nodes}
    result_definitions: Dict[str, str] = {}
    result_frequencies: Dict[str, int] = {}
    removed_ids: set = set()
    stats = ApplyStats()

    for decision in decisions:
        keep_id = decision.result_node
        targets = list(decision.affected_nodes)

        if decision.action == DecisionAction.REMOVE:
            for node_id in targets:
                if node_id in node_by_id and node_id not in removed_ids:
                    removed_ids.add(node_id)
                    stats.removed_nodes += 1
            continue

        # 保留侧可能已被更早的决策删除（跨教材链式匹配），跳过以免误删
        if not keep_id or keep_id not in node_by_id or keep_id in removed_ids:
            continue

        if decision.action == DecisionAction.MERGE:
            sources = [node_by_id[nid] for nid in targets if nid in node_by_id]
            merged_text = merge_definitions(
                node_by_id[keep_id].definition,
                *[n.definition for n in sources if n.id != keep_id],
            )
            if merged_text and merged_text != node_by_id[keep_id].definition:
                result_definitions[keep_id] = merged_text
                stats.enriched_nodes += 1
            stats.merged_nodes += 1
        else:
            stats.kept_nodes += 1

        # 频次累加：整合后的频次代表该概念在多少本教材中出现过
        frequency = node_by_id[keep_id].frequency or 1
        for node_id in targets:
            if node_id != keep_id and node_id in node_by_id:
                removed_ids.add(node_id)
                frequency += node_by_id[node_id].frequency or 1
        if frequency != (node_by_id[keep_id].frequency or 1):
            result_frequencies[keep_id] = frequency

    retained: List[KnowledgeNode] = []
    for node in nodes:
        if node.id in removed_ids:
            continue
        updates: Dict[str, Any] = {}
        if node.id in result_definitions:
            updates["definition"] = result_definitions[node.id]
        if node.id in result_frequencies:
            updates["frequency"] = result_frequencies[node.id]
        retained.append(node.model_copy(update=updates) if updates else node)

    retained_ids = {n.id for n in retained}
    retained_relations = [
        rel for rel in relations
        if rel.source in retained_ids and rel.target in retained_ids
    ]

    logger.info(
        "决策应用完成: 保留 %d/%d 节点，关系 %d/%d（merge=%d, keep=%d, remove=%d）",
        len(retained), len(nodes), len(retained_relations), len(relations),
        stats.merged_nodes, stats.kept_nodes, stats.removed_nodes,
    )
    return retained, retained_relations, stats


async def generate_integration_decisions(
    aligned_pairs: List[Any], nodes_map: Dict[str, KnowledgeNode]
) -> DecisionResult:
    """便捷函数：生成整合决策。"""
    maker = DecisionMaker()
    return await maker.make_decisions_for_aligned_pairs(aligned_pairs, nodes_map)

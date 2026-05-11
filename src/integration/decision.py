"""
整合决策机制模块

实现知识点整合决策功能：
- 决策数据结构
- 决策生成逻辑
- 决策理由生成
"""

import logging
import uuid
from typing import List, Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

from src.kg.models import KnowledgeNode
from src.llm.client import call_llm

logger = logging.getLogger(__name__)


class DecisionAction(str, Enum):
    """决策动作类型"""
    MERGE = "merge"      # 合并重复
    KEEP = "keep"        # 保留唯一
    REMOVE = "remove"    # 删除冗余


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
            "created_at": self.created_at.isoformat()
        }


@dataclass
class DecisionResult:
    """决策结果"""
    decisions: List[IntegrationDecision]
    total_decisions: int
    merge_count: int
    keep_count: int
    remove_count: int


class DecisionMaker:
    """决策生成器"""
    
    def __init__(self):
        pass
    
    async def generate_decision_reason(
        self,
        action: DecisionAction,
        nodes: List[KnowledgeNode]
    ) -> Tuple[str, float]:
        """
        使用LLM生成决策理由
        
        Args:
            action: 决策动作
            nodes: 涉及的知识点
            
        Returns:
            (reason, confidence)
        """
        nodes_info = "\n".join([
            f"- {node.name}: {node.definition[:50]}..." if len(node.definition) > 50 else f"- {node.name}: {node.definition}"
            for node in nodes
        ])
        
        if action == DecisionAction.MERGE:
            prompt = f"""以下知识点描述的是同一个概念，请给出合并的理由：

{nodes_info}

请以JSON格式返回：
{{
    "reason": "合并理由",
    "confidence": 0.0-1.0
}}"""
        elif action == DecisionAction.KEEP:
            prompt = f"""以下知识点中，需要保留最佳版本，请给出保留理由：

{nodes_info}

请以JSON格式返回：
{{
    "reason": "保留理由",
    "confidence": 0.0-1.0
}}"""
        else:
            prompt = f"""以下知识点存在冗余，请给出删除理由：

{nodes_info}

请以JSON格式返回：
{{
    "reason": "删除理由",
    "confidence": 0.0-1.0
}}"""
        
        try:
            response = await call_llm(
                prompt=prompt,
                system_prompt="你是一个教育知识整合专家，擅长判断知识点的整合策略。"
            )
            
            import json
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            
            result = json.loads(response.strip())
            return (result.get("reason", "无理由"), result.get("confidence", 0.5))
        except Exception as e:
            logger.error(f"Failed to generate decision reason: {e}")
            return (f"基于规则判断: {action.value}", 0.5)
    
    async def make_decisions_for_aligned_pairs(
        self,
        aligned_pairs: List[Any],
        nodes_map: Dict[str, KnowledgeNode]
    ) -> DecisionResult:
        """
        为对齐的知识点对生成整合决策
        
        Args:
            aligned_pairs: 对齐的知识点对列表
            nodes_map: 节点ID到节点的映射
            
        Returns:
            决策结果
        """
        decisions = []
        
        for pair in aligned_pairs:
            node1 = nodes_map.get(pair.node1_id)
            node2 = nodes_map.get(pair.node2_id)
            
            if not node1 or not node2:
                continue
            
            if pair.confidence >= 0.9:
                action = DecisionAction.MERGE
            elif pair.confidence >= 0.7:
                action = DecisionAction.KEEP
            else:
                action = DecisionAction.REMOVE
            
            if action == DecisionAction.MERGE:
                affected_nodes = [pair.node1_id, pair.node2_id]
                result_node = pair.node1_id
            elif action == DecisionAction.KEEP:
                if len(node1.definition) >= len(node2.definition):
                    affected_nodes = [pair.node1_id, pair.node2_id]
                    result_node = pair.node1_id
                else:
                    affected_nodes = [pair.node2_id, pair.node1_id]
                    result_node = pair.node2_id
            else:
                affected_nodes = [pair.node2_id]
                result_node = pair.node1_id
            
            reason, confidence = await self.generate_decision_reason(
                action,
                [node1, node2]
            )
            
            decision = IntegrationDecision(
                decision_id=f"decision_{uuid.uuid4().hex[:8]}",
                action=action,
                affected_nodes=affected_nodes,
                result_node=result_node,
                reason=reason,
                confidence=confidence
            )
            decisions.append(decision)
        
        merge_count = sum(1 for d in decisions if d.action == DecisionAction.MERGE)
        keep_count = sum(1 for d in decisions if d.action == DecisionAction.KEEP)
        remove_count = sum(1 for d in decisions if d.action == DecisionAction.REMOVE)
        
        logger.info(f"Generated {len(decisions)} decisions: merge={merge_count}, keep={keep_count}, remove={remove_count}")
        
        return DecisionResult(
            decisions=decisions,
            total_decisions=len(decisions),
            merge_count=merge_count,
            keep_count=keep_count,
            remove_count=remove_count
        )


from typing import Tuple


async def generate_integration_decisions(
    aligned_pairs: List[Any],
    nodes_map: Dict[str, KnowledgeNode]
) -> DecisionResult:
    """
    便捷函数：生成整合决策
    
    Args:
        aligned_pairs: 对齐的知识点对列表
        nodes_map: 节点ID到节点的映射
        
    Returns:
        决策结果
    """
    maker = DecisionMaker()
    return await maker.make_decisions_for_aligned_pairs(aligned_pairs, nodes_map)

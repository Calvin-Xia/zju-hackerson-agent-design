"""
压缩比控制模块

实现整合压缩比监控和控制功能：
- 字数统计
- 压缩比计算
- 压缩策略优化
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from src.kg.models import KnowledgeNode, KnowledgeRelation

logger = logging.getLogger(__name__)


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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_node_count": self.original_node_count,
            "original_relation_count": self.original_relation_count,
            "original_total_chars": self.original_total_chars,
            "compressed_node_count": self.compressed_node_count,
            "compressed_relation_count": self.compressed_relation_count,
            "compressed_total_chars": self.compressed_total_chars,
            "compression_ratio": self.compression_ratio,
            "is_within_limit": self.is_within_limit
        }


class CompressionController:
    """压缩比控制器"""
    
    def __init__(self, max_compression_ratio: float = 0.3):
        """
        初始化压缩比控制器
        
        Args:
            max_compression_ratio: 最大压缩比（默认30%）
        """
        self.max_compression_ratio = max_compression_ratio
    
    def count_chars(self, nodes: List[KnowledgeNode]) -> int:
        """统计知识点总字数"""
        total = 0
        for node in nodes:
            total += len(node.name) + len(node.definition)
        return total
    
    def compute_compression_stats(
        self,
        original_nodes: List[KnowledgeNode],
        original_relations: List[KnowledgeRelation],
        compressed_nodes: List[KnowledgeNode],
        compressed_relations: List[KnowledgeRelation]
    ) -> CompressionStats:
        """
        计算压缩统计
        
        Args:
            original_nodes: 原始知识点
            original_relations: 原始关系
            compressed_nodes: 压缩后知识点
            compressed_relations: 压缩后关系
            
        Returns:
            压缩统计
        """
        original_chars = self.count_chars(original_nodes)
        compressed_chars = self.count_chars(compressed_nodes)
        
        if original_chars == 0:
            compression_ratio = 0.0
        else:
            compression_ratio = compressed_chars / original_chars
        
        is_within_limit = compression_ratio <= self.max_compression_ratio
        
        return CompressionStats(
            original_node_count=len(original_nodes),
            original_relation_count=len(original_relations),
            original_total_chars=original_chars,
            compressed_node_count=len(compressed_nodes),
            compressed_relation_count=len(compressed_relations),
            compressed_total_chars=compressed_chars,
            compression_ratio=compression_ratio,
            is_within_limit=is_within_limit
        )
    
    def select_nodes_for_compression(
        self,
        nodes: List[KnowledgeNode],
        target_chars: int
    ) -> List[KnowledgeNode]:
        """
        选择要保留的知识点以达到目标字数
        
        Args:
            nodes: 知识点列表
            target_chars: 目标字数
            
        Returns:
            保留的知识点列表
        """
        sorted_nodes = sorted(nodes, key=lambda n: n.frequency, reverse=True)
        
        selected = []
        current_chars = 0
        
        for node in sorted_nodes:
            node_chars = len(node.name) + len(node.definition)
            if current_chars + node_chars <= target_chars:
                selected.append(node)
                current_chars += node_chars
            else:
                break
        
        logger.info(f"Selected {len(selected)}/{len(nodes)} nodes, {current_chars}/{target_chars} chars")
        
        return selected
    
    def optimize_compression(
        self,
        nodes: List[KnowledgeNode],
        relations: List[KnowledgeRelation]
    ) -> tuple[List[KnowledgeNode], List[KnowledgeRelation]]:
        """
        优化压缩，确保不超过30%压缩比
        
        Args:
            nodes: 知识点列表
            relations: 关系列表
            
        Returns:
            优化后的知识点和关系
        """
        original_chars = self.count_chars(nodes)
        target_chars = int(original_chars * self.max_compression_ratio)
        
        if self.count_chars(nodes) <= target_chars:
            return nodes, relations
        
        selected_nodes = self.select_nodes_for_compression(nodes, target_chars)
        selected_node_ids = {node.id for node in selected_nodes}
        
        selected_relations = [
            rel for rel in relations
            if rel.source in selected_node_ids and rel.target in selected_node_ids
        ]
        
        logger.info(f"Compression optimized: {len(nodes)} -> {len(selected_nodes)} nodes, {len(relations)} -> {len(selected_relations)} relations")
        
        return selected_nodes, selected_relations


def compute_compression_ratio(
    original_nodes: List[KnowledgeNode],
    compressed_nodes: List[KnowledgeNode]
) -> float:
    """
    便捷函数：计算压缩比
    
    Args:
        original_nodes: 原始知识点
        compressed_nodes: 压缩后知识点
        
    Returns:
        压缩比 (0-1)
    """
    controller = CompressionController()
    original_chars = controller.count_chars(original_nodes)
    compressed_chars = controller.count_chars(compressed_nodes)
    
    if original_chars == 0:
        return 0.0
    
    return compressed_chars / original_chars

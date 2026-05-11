"""
语义对齐算法模块

实现跨教材知识点对齐功能：
- 文本嵌入相似度计算
- LLM等价判断
- 混合对齐策略
"""

import logging
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import numpy as np

from src.embedding.service import get_embedding_service
from src.kg.models import KnowledgeNode
from src.llm.client import call_llm

logger = logging.getLogger(__name__)


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


@dataclass
class AlignmentResult:
    """对齐结果"""
    aligned_pairs: List[AlignedPair]
    total_pairs_checked: int
    equivalent_count: int
    avg_similarity: float


class SemanticAligner:
    """语义对齐器"""
    
    def __init__(self, similarity_threshold: float = 0.8, use_llm_verification: bool = True):
        """
        初始化语义对齐器
        
        Args:
            similarity_threshold: 嵌入相似度阈值
            use_llm_verification: 是否使用LLM验证
        """
        self.similarity_threshold = similarity_threshold
        self.use_llm_verification = use_llm_verification
        self.embedding_service = get_embedding_service()
    
    def compute_similarity_matrix(self, nodes1: List[KnowledgeNode], nodes2: List[KnowledgeNode]) -> np.ndarray:
        """
        计算两组知识点的相似度矩阵
        
        Args:
            nodes1: 第一组知识点
            nodes2: 第二组知识点
            
        Returns:
            相似度矩阵 (len(nodes1), len(nodes2))
        """
        texts1 = [f"{node.name}: {node.definition}" for node in nodes1]
        texts2 = [f"{node.name}: {node.definition}" for node in nodes2]
        
        embeddings1 = self.embedding_service.encode(texts1)
        embeddings2 = self.embedding_service.encode(texts2)
        
        return self.embedding_service.batch_similarity(embeddings1, embeddings2)
    
    def find_candidate_pairs(
        self,
        nodes1: List[KnowledgeNode],
        nodes2: List[KnowledgeNode],
        threshold: Optional[float] = None
    ) -> List[Tuple[int, int, float]]:
        """
        使用嵌入相似度快速筛选候选对
        
        Args:
            nodes1: 第一组知识点
            nodes2: 第二组知识点
            threshold: 相似度阈值
            
        Returns:
            候选对列表 [(idx1, idx2, similarity), ...]
        """
        if threshold is None:
            threshold = self.similarity_threshold
        
        similarity_matrix = self.compute_similarity_matrix(nodes1, nodes2)
        
        candidates = []
        for i in range(len(nodes1)):
            for j in range(len(nodes2)):
                sim = similarity_matrix[i, j]
                if sim >= threshold:
                    candidates.append((i, j, float(sim)))
        
        candidates.sort(key=lambda x: x[2], reverse=True)
        logger.info(f"Found {len(candidates)} candidate pairs with similarity >= {threshold}")
        
        return candidates
    
    async def verify_equivalence_with_llm(
        self,
        node1: KnowledgeNode,
        node2: KnowledgeNode
    ) -> Tuple[bool, float, str]:
        """
        使用LLM判断两个知识点是否等价
        
        Args:
            node1: 第一个知识点
            node2: 第二个知识点
            
        Returns:
            (is_equivalent, confidence, reason)
        """
        prompt = f"""请判断以下两个知识点是否描述同一个概念。

知识点1：
- 名称：{node1.name}
- 定义：{node1.definition}
- 章节：{node1.chapter}

知识点2：
- 名称：{node2.name}
- 定义：{node2.definition}
- 章节：{node2.chapter}

请以JSON格式返回判断结果：
{{
    "is_equivalent": true/false,
    "confidence": 0.0-1.0,
    "reason": "判断理由"
}}

注意：
- 如果两个知识点描述同一个概念，即使措辞不同，也应判断为等价
- 如果一个是另一个的子集或超集，也应判断为等价
- 请给出置信度分数和详细理由"""

        try:
            response = await call_llm(prompt=prompt, system_prompt="你是一个教育知识专家，擅长判断知识点的等价性。")
            
            import json
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            
            result = json.loads(response.strip())
            
            return (
                result.get("is_equivalent", False),
                result.get("confidence", 0.5),
                result.get("reason", "无理由")
            )
        except Exception as e:
            logger.error(f"LLM verification failed: {e}")
            return (False, 0.0, f"LLM验证失败: {str(e)}")
    
    async def align_nodes(
        self,
        nodes1: List[KnowledgeNode],
        nodes2: List[KnowledgeNode]
    ) -> AlignmentResult:
        """
        对齐两组知识点
        
        Args:
            nodes1: 第一组知识点
            nodes2: 第二组知识点
            
        Returns:
            对齐结果
        """
        candidates = self.find_candidate_pairs(nodes1, nodes2)
        
        aligned_pairs = []
        for idx1, idx2, similarity in candidates:
            node1 = nodes1[idx1]
            node2 = nodes2[idx2]
            
            if self.use_llm_verification:
                is_equivalent, confidence, reason = await self.verify_equivalence_with_llm(node1, node2)
            else:
                is_equivalent = similarity >= self.similarity_threshold
                confidence = similarity
                reason = f"基于嵌入相似度: {similarity:.3f}"
            
            if is_equivalent:
                pair = AlignedPair(
                    node1_id=node1.id,
                    node2_id=node2.id,
                    node1_name=node1.name,
                    node2_name=node2.name,
                    similarity_score=similarity,
                    is_equivalent=is_equivalent,
                    confidence=confidence,
                    reason=reason
                )
                aligned_pairs.append(pair)
        
        total_pairs = len(candidates)
        equivalent_count = len(aligned_pairs)
        avg_similarity = np.mean([p.similarity_score for p in aligned_pairs]) if aligned_pairs else 0.0
        
        logger.info(f"Alignment completed: {equivalent_count}/{total_pairs} pairs equivalent")
        
        return AlignmentResult(
            aligned_pairs=aligned_pairs,
            total_pairs_checked=total_pairs,
            equivalent_count=equivalent_count,
            avg_similarity=float(avg_similarity)
        )
    
    async def align_multiple_textbooks(
        self,
        textbook_nodes: Dict[str, List[KnowledgeNode]]
    ) -> List[AlignmentResult]:
        """
        对齐多本教材的知识点
        
        Args:
            textbook_nodes: 教材ID到知识点列表的映射
            
        Returns:
            对齐结果列表
        """
        textbook_ids = list(textbook_nodes.keys())
        results = []
        
        for i in range(len(textbook_ids)):
            for j in range(i + 1, len(textbook_ids)):
                id1 = textbook_ids[i]
                id2 = textbook_ids[j]
                
                logger.info(f"Aligning textbooks: {id1} vs {id2}")
                
                result = await self.align_nodes(
                    textbook_nodes[id1],
                    textbook_nodes[id2]
                )
                results.append(result)
        
        return results


async def align_knowledge_nodes(
    nodes1: List[KnowledgeNode],
    nodes2: List[KnowledgeNode],
    similarity_threshold: float = 0.8,
    use_llm: bool = True
) -> AlignmentResult:
    """
    便捷函数：对齐两组知识点
    
    Args:
        nodes1: 第一组知识点
        nodes2: 第二组知识点
        similarity_threshold: 相似度阈值
        use_llm: 是否使用LLM验证
        
    Returns:
        对齐结果
    """
    aligner = SemanticAligner(
        similarity_threshold=similarity_threshold,
        use_llm_verification=use_llm
    )
    return await aligner.align_nodes(nodes1, nodes2)

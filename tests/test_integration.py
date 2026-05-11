"""
整合模块测试

测试语义对齐、决策生成、压缩比控制功能
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

from src.integration.alignment import SemanticAligner, AlignedPair, AlignmentResult
from src.integration.decision import DecisionMaker, DecisionAction, IntegrationDecision, DecisionResult
from src.integration.compression import CompressionController, CompressionStats
from src.kg.models import KnowledgeNode, KnowledgeRelation


@pytest.fixture
def sample_nodes1():
    return [
        KnowledgeNode(
            id="node_1",
            name="炎症",
            definition="炎症是机体对致炎因子的损伤所发生的防御性反应",
            category="核心概念",
            chapter="第四章",
            textbook_id="book_1"
        ),
        KnowledgeNode(
            id="node_2",
            name="免疫",
            definition="免疫是机体识别和排除抗原性异物的功能",
            category="核心概念",
            chapter="第五章",
            textbook_id="book_1"
        ),
    ]


@pytest.fixture
def sample_nodes2():
    return [
        KnowledgeNode(
            id="node_3",
            name="炎症反应",
            definition="炎症是具有血管系统的活体组织对各种损伤因子的刺激所发生的防御性反应",
            category="核心概念",
            chapter="第三章",
            textbook_id="book_2"
        ),
        KnowledgeNode(
            id="node_4",
            name="免疫系统",
            definition="免疫系统是机体执行免疫应答及免疫功能的重要系统",
            category="核心概念",
            chapter="第六章",
            textbook_id="book_2"
        ),
    ]


@pytest.fixture
def sample_relations():
    return [
        KnowledgeRelation(
            source="node_1",
            target="node_2",
            relation_type="prerequisite",
            description="炎症是免疫的基础"
        ),
    ]


class TestCompressionController:
    """压缩比控制器测试"""
    
    def test_count_chars(self, sample_nodes1):
        controller = CompressionController()
        chars = controller.count_chars(sample_nodes1)
        assert chars > 0
        assert chars == len("炎症") + len("炎症是机体对致炎因子的损伤所发生的防御性反应") + \
               len("免疫") + len("免疫是机体识别和排除抗原性异物的功能")
    
    def test_compute_compression_stats(self, sample_nodes1, sample_relations):
        controller = CompressionController()
        stats = controller.compute_compression_stats(
            sample_nodes1, sample_relations,
            sample_nodes1, sample_relations
        )
        
        assert stats.original_node_count == 2
        assert stats.compressed_node_count == 2
        assert stats.compression_ratio > 0
        assert stats.compression_ratio == 1.0
    
    def test_select_nodes_for_compression(self, sample_nodes1):
        controller = CompressionController()
        
        for node in sample_nodes1:
            node.frequency = 1
        
        target_chars = 50
        selected = controller.select_nodes_for_compression(sample_nodes1, target_chars)
        
        assert len(selected) <= len(sample_nodes1)
        total_chars = sum(len(n.name) + len(n.definition) for n in selected)
        assert total_chars <= target_chars
    
    def test_optimize_compression(self, sample_nodes1, sample_relations):
        controller = CompressionController(max_compression_ratio=0.5)
        
        for node in sample_nodes1:
            node.frequency = 1
        
        optimized_nodes, optimized_relations = controller.optimize_compression(
            sample_nodes1, sample_relations
        )
        
        assert len(optimized_nodes) <= len(sample_nodes1)
        assert len(optimized_relations) <= len(sample_relations)


class TestSemanticAligner:
    """语义对齐器测试"""
    
    def test_compute_similarity_matrix(self, sample_nodes1, sample_nodes2):
        mock_service = MagicMock()
        mock_service.encode.return_value = np.random.rand(2, 384)
        mock_service.batch_similarity.return_value = np.array([[0.9, 0.3], [0.2, 0.8]])
        
        aligner = SemanticAligner()
        aligner.embedding_service = mock_service
        similarity_matrix = aligner.compute_similarity_matrix(sample_nodes1, sample_nodes2)
        
        assert similarity_matrix.shape == (2, 2)
        assert np.all(similarity_matrix >= 0)
        assert np.all(similarity_matrix <= 1)
    
    def test_find_candidate_pairs(self, sample_nodes1, sample_nodes2):
        mock_service = MagicMock()
        mock_service.encode.return_value = np.random.rand(2, 384)
        mock_service.batch_similarity.return_value = np.array([[0.9, 0.3], [0.2, 0.8]])
        
        aligner = SemanticAligner(similarity_threshold=0.7)
        aligner.embedding_service = mock_service
        candidates = aligner.find_candidate_pairs(sample_nodes1, sample_nodes2)
        
        assert len(candidates) > 0
        for idx1, idx2, sim in candidates:
            assert sim >= 0.7


class TestDecisionMaker:
    """决策生成器测试"""
    
    @pytest.mark.asyncio
    @patch('src.integration.decision.call_llm')
    async def test_generate_decision_reason(self, mock_call_llm, sample_nodes1):
        mock_call_llm.return_value = '{"reason": "这两个知识点描述相同概念", "confidence": 0.9}'
        
        maker = DecisionMaker()
        reason, confidence = await maker.generate_decision_reason(
            DecisionAction.MERGE,
            sample_nodes1
        )
        
        assert isinstance(reason, str)
        assert 0 <= confidence <= 1
    
    @pytest.mark.asyncio
    @patch('src.integration.decision.call_llm')
    async def test_make_decisions_for_aligned_pairs(self, mock_call_llm, sample_nodes1, sample_nodes2):
        mock_call_llm.return_value = '{"reason": "测试理由", "confidence": 0.9}'
        
        aligned_pairs = [
            AlignedPair(
                node1_id="node_1",
                node2_id="node_3",
                node1_name="炎症",
                node2_name="炎症反应",
                similarity_score=0.9,
                is_equivalent=True,
                confidence=0.95,
                reason="语义相似"
            )
        ]
        
        nodes_map = {
            "node_1": sample_nodes1[0],
            "node_3": sample_nodes2[0]
        }
        
        maker = DecisionMaker()
        result = await maker.make_decisions_for_aligned_pairs(aligned_pairs, nodes_map)
        
        assert isinstance(result, DecisionResult)
        assert result.total_decisions == 1
        assert result.merge_count + result.keep_count + result.remove_count == 1


class TestIntegrationAPI:
    """整合API测试"""
    
    def test_merge_request_validation(self):
        from src.api.routes.integration import MergeRequest
        
        request = MergeRequest(textbook_ids=["book_1", "book_2"])
        assert len(request.textbook_ids) == 2
    
    def test_task_status_model(self):
        from src.api.routes.integration import TaskStatus
        
        status = TaskStatus(
            task_id="test_123",
            status="completed",
            progress=100.0
        )
        assert status.task_id == "test_123"
        assert status.status == "completed"
    
    def test_decision_response_model(self):
        from src.api.routes.integration import DecisionResponse
        
        decision = DecisionResponse(
            decision_id="decision_1",
            action="merge",
            affected_nodes=["node_1", "node_2"],
            result_node="node_1",
            reason="测试理由",
            confidence=0.9
        )
        assert decision.action == "merge"
        assert len(decision.affected_nodes) == 2

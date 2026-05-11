import pytest
import tempfile
import shutil
from pathlib import Path
from src.kg.graph_store import KnowledgeGraphStore
from src.kg.models import KnowledgeGraph, KnowledgeNode, KnowledgeRelation


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d)


@pytest.fixture
def store(temp_dir):
    """创建存储实例"""
    return KnowledgeGraphStore(data_dir=str(temp_dir))


@pytest.fixture
def sample_graph():
    """创建示例图谱"""
    return KnowledgeGraph(
        textbook_id="test_book",
        textbook_title="测试教材",
        nodes=[
            KnowledgeNode(
                id="node_1",
                name="概念A",
                definition="定义A",
                category="核心概念",
                chapter="第一章",
                textbook_id="test_book",
                frequency=1
            ),
            KnowledgeNode(
                id="node_2",
                name="概念B",
                definition="定义B",
                category="定理",
                chapter="第二章",
                textbook_id="test_book",
                frequency=2
            ),
            KnowledgeNode(
                id="node_3",
                name="概念C",
                definition="定义C",
                category="方法",
                chapter="第一章",
                textbook_id="test_book",
                frequency=1
            ),
        ],
        relations=[
            KnowledgeRelation(
                source="node_1",
                target="node_2",
                relation_type="prerequisite",
                description="A是B的前置知识",
                confidence=0.9
            ),
            KnowledgeRelation(
                source="node_2",
                target="node_3",
                relation_type="parallel",
                description="B和C是并列关系",
                confidence=0.8
            ),
        ],
    )


class TestKnowledgeGraphStore:
    """KnowledgeGraphStore 测试类"""

    def test_save_and_load(self, store, sample_graph):
        """测试保存和加载"""
        store.save("test_1", sample_graph)
        loaded = store.load("test_1")
        
        assert loaded is not None
        assert loaded.textbook_id == "test_book"
        assert loaded.textbook_title == "测试教材"
        assert len(loaded.nodes) == 3
        assert len(loaded.relations) == 2

    def test_load_nonexistent(self, store):
        """测试加载不存在的图谱"""
        result = store.load("nonexistent")
        assert result is None

    def test_list_graphs(self, store, sample_graph):
        """测试列出图谱"""
        store.save("test_1", sample_graph)
        store.save("test_2", sample_graph)
        
        graphs = store.list_graphs()
        assert len(graphs) == 2
        assert "test_1" in graphs
        assert "test_2" in graphs

    def test_list_graphs_empty(self, store):
        """测试空目录列出图谱"""
        graphs = store.list_graphs()
        assert len(graphs) == 0

    def test_delete(self, store, sample_graph):
        """测试删除图谱"""
        store.save("test_1", sample_graph)
        assert store.delete("test_1") is True
        assert store.load("test_1") is None

    def test_delete_nonexistent(self, store):
        """测试删除不存在的图谱"""
        assert store.delete("nonexistent") is False

    def test_update_node(self, store, sample_graph):
        """测试更新节点"""
        store.save("test_1", sample_graph)
        
        success = store.update_node("test_1", "node_1", {"name": "新名称", "definition": "新定义"})
        assert success is True
        
        loaded = store.load("test_1")
        assert loaded is not None
        node = next(n for n in loaded.nodes if n.id == "node_1")
        assert node.name == "新名称"
        assert node.definition == "新定义"

    def test_update_node_partial(self, store, sample_graph):
        """测试部分更新节点"""
        store.save("test_1", sample_graph)
        
        success = store.update_node("test_1", "node_1", {"name": "新名称"})
        assert success is True
        
        loaded = store.load("test_1")
        node = next(n for n in loaded.nodes if n.id == "node_1")
        assert node.name == "新名称"
        assert node.definition == "定义A"  # 未更新的字段保持不变

    def test_update_node_nonexistent_graph(self, store):
        """测试更新不存在图谱的节点"""
        success = store.update_node("nonexistent", "node_1", {"name": "新名称"})
        assert success is False

    def test_update_node_nonexistent_node(self, store, sample_graph):
        """测试更新不存在的节点"""
        store.save("test_1", sample_graph)
        success = store.update_node("test_1", "nonexistent", {"name": "新名称"})
        assert success is False

    def test_update_relation(self, store, sample_graph):
        """测试更新关系"""
        store.save("test_1", sample_graph)
        
        success = store.update_relation(
            "test_1", "node_1", "node_2", "prerequisite",
            {"description": "新描述", "confidence": 0.95}
        )
        assert success is True
        
        loaded = store.load("test_1")
        rel = next(r for r in loaded.relations if r.source == "node_1" and r.target == "node_2")
        assert rel.description == "新描述"
        assert rel.confidence == 0.95

    def test_update_relation_nonexistent(self, store, sample_graph):
        """测试更新不存在的关系"""
        store.save("test_1", sample_graph)
        success = store.update_relation(
            "test_1", "nonexistent", "node_2", "prerequisite",
            {"description": "新描述"}
        )
        assert success is False

    def test_save_preserves_timestamp(self, store, sample_graph):
        """测试保存时记录时间戳"""
        store.save("test_1", sample_graph)
        loaded = store.load("test_1")
        
        assert loaded.extracted_at is not None

    def test_multiple_graphs(self, store, sample_graph):
        """测试多个图谱的独立性"""
        graph2 = KnowledgeGraph(
            textbook_id="test_book_2",
            textbook_title="测试教材2",
            nodes=[
                KnowledgeNode(id="node_x", name="概念X", textbook_id="test_book_2"),
            ],
            relations=[],
        )
        
        store.save("test_1", sample_graph)
        store.save("test_2", graph2)
        
        loaded1 = store.load("test_1")
        loaded2 = store.load("test_2")
        
        assert len(loaded1.nodes) == 3
        assert len(loaded2.nodes) == 1
        assert loaded1.textbook_id == "test_book"
        assert loaded2.textbook_id == "test_book_2"

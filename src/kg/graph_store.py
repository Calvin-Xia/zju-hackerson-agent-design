import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.kg.models import KnowledgeGraph

logger = logging.getLogger(__name__)


class KnowledgeGraphStore:
    """知识图谱存储"""

    def __init__(self, data_dir: str = "data/knowledge_graphs"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, file_id: str) -> Path:
        return self.data_dir / f"{file_id}_kg.json"

    def save(self, file_id: str, graph: KnowledgeGraph) -> None:
        """保存知识图谱到JSON文件"""
        graph.extracted_at = datetime.now()
        path = self._get_path(file_id)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(graph.model_dump_json(indent=2))

        logger.info(f"Knowledge graph saved: {path}")

    def load(self, file_id: str) -> Optional[KnowledgeGraph]:
        """加载知识图谱"""
        path = self._get_path(file_id)

        if not path.exists():
            return None

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return KnowledgeGraph.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to load knowledge graph: {e}")
            return None

    def list_graphs(self) -> List[str]:
        """列出所有已存储的教材ID"""
        file_ids = []
        for path in self.data_dir.glob("*_kg.json"):
            file_id = path.name.replace("_kg.json", "")
            file_ids.append(file_id)
        return file_ids

    def delete(self, file_id: str) -> bool:
        """删除知识图谱"""
        path = self._get_path(file_id)

        if path.exists():
            path.unlink()
            logger.info(f"Knowledge graph deleted: {path}")
            return True

        return False

    def update_node(self, file_id: str, node_id: str, updates: dict) -> bool:
        """更新节点"""
        graph = self.load(file_id)
        if not graph:
            return False
        for node in graph.nodes:
            if node.id == node_id:
                for key, value in updates.items():
                    if hasattr(node, key):
                        setattr(node, key, value)
                self.save(file_id, graph)
                return True
        return False

    def update_relation(self, file_id: str, source: str, target: str, relation_type: str, updates: dict) -> bool:
        """更新关系"""
        graph = self.load(file_id)
        if not graph:
            return False
        for rel in graph.relations:
            if rel.source == source and rel.target == target and rel.relation_type == relation_type:
                for key, value in updates.items():
                    if hasattr(rel, key):
                        setattr(rel, key, value)
                self.save(file_id, graph)
                return True
        return False


graph_store = KnowledgeGraphStore()

"""知识图谱持久化。

每个教材的图谱保存为 ``data/knowledge_graphs/{file_id}_kg.json``。

写入采用「临时文件 + 原子替换」，配合进程内锁，避免并发更新时
写到一半的 JSON 被后续读取（旧实现非原子写入，一次中断就会让图谱
变成"不存在"，前端只能重新抽取）。
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.kg.models import KnowledgeGraph
from src.shared.config import settings

logger = logging.getLogger(__name__)


class KnowledgeGraphStore:
    """知识图谱存储"""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir) if data_dir else settings.knowledge_graphs_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _get_path(self, file_id: str) -> Path:
        return self.data_dir / f"{file_id}_kg.json"

    def save(self, file_id: str, graph: KnowledgeGraph) -> None:
        """原子地保存知识图谱到 JSON 文件。"""
        graph.extracted_at = datetime.now()
        path = self._get_path(file_id)

        with self._lock:
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            try:
                tmp_path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
                os.replace(tmp_path, path)  # 同目录下的原子替换
            except OSError:
                tmp_path.unlink(missing_ok=True)
                logger.exception("保存知识图谱失败: %s", path)
                raise

        logger.info("知识图谱已保存: %s", path)

    def load(self, file_id: str) -> Optional[KnowledgeGraph]:
        """加载知识图谱；文件不存在时返回 ``None``，损坏时抛出异常。"""
        path = self._get_path(file_id)

        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return KnowledgeGraph.model_validate(data)
        except (json.JSONDecodeError, ValueError) as exc:
            # 损坏与"不存在"必须区分：静默返回 None 会让调用方以为图谱丢失而重复抽取
            logger.error("知识图谱文件损坏 %s: %s", path, exc)
            raise

    def load_safe(self, file_id: str) -> Optional[KnowledgeGraph]:
        """遍历场景下使用：文件损坏时返回 ``None`` 而不是抛出，避免一个坏文件中断整个列表。"""
        try:
            return self.load(file_id)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("跳过损坏的知识图谱 %s: %s", file_id, exc)
            return None

    def list_graphs(self) -> List[str]:
        """列出所有已存储的教材 ID。"""
        return [
            path.name.removesuffix("_kg.json")
            for path in sorted(self.data_dir.glob("*_kg.json"))
        ]

    def delete(self, file_id: str) -> bool:
        """删除知识图谱。"""
        path = self._get_path(file_id)

        if path.exists():
            with self._lock:
                path.unlink()
            logger.info("知识图谱已删除: %s", path)
            return True

        return False

    def update_node(self, file_id: str, node_id: str, updates: dict) -> bool:
        """更新节点字段（整图读改写，持锁避免并发覆盖）。"""
        with self._lock:
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

    def update_relation(
        self,
        file_id: str,
        source: str,
        target: str,
        relation_type: str,
        updates: dict,
    ) -> bool:
        """更新关系字段。"""
        with self._lock:
            graph = self.load(file_id)
            if not graph:
                return False
            for rel in graph.relations:
                if (
                    rel.source == source
                    and rel.target == target
                    and rel.relation_type == relation_type
                ):
                    for key, value in updates.items():
                        if hasattr(rel, key):
                            setattr(rel, key, value)
                    self.save(file_id, graph)
                    return True
            return False


graph_store = KnowledgeGraphStore()

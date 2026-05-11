"""
状态持久化模块

提供异步任务状态的持久化存储
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StateStore:
    """状态持久化存储"""
    
    def __init__(self, storage_path: str = "data/tasks"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def _get_file_path(self, task_id: str) -> Path:
        return self.storage_path / f"{task_id}.json"
    
    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        if task_id in self._cache:
            return self._cache[task_id]
        
        file_path = self._get_file_path(task_id)
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._cache[task_id] = data
                return data
            except Exception as e:
                logger.error(f"Failed to load task state {task_id}: {e}")
        
        return None
    
    def set(self, task_id: str, data: Dict[str, Any]) -> None:
        """保存任务状态"""
        self._cache[task_id] = data
        
        file_path = self._get_file_path(task_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save task state {task_id}: {e}")
    
    def update(self, task_id: str, updates: Dict[str, Any]) -> None:
        """更新任务状态"""
        data = self.get(task_id) or {}
        data.update(updates)
        self.set(task_id, data)
    
    def exists(self, task_id: str) -> bool:
        """检查任务是否存在"""
        return task_id in self._cache or self._get_file_path(task_id).exists()


# 全局实例
_integration_store: Optional[StateStore] = None
_indexing_store: Optional[StateStore] = None


def get_integration_store() -> StateStore:
    global _integration_store
    if _integration_store is None:
        _integration_store = StateStore("data/tasks/integration")
    return _integration_store


def get_indexing_store() -> StateStore:
    global _indexing_store
    if _indexing_store is None:
        _indexing_store = StateStore("data/tasks/indexing")
    return _indexing_store

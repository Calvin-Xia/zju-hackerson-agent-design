"""
状态持久化模块

提供异步任务状态的持久化存储。

任务状态会被后台线程（``asyncio.to_thread``）与事件循环并发读写，
因此这里用可重入锁保护缓存，并用「临时文件 + 原子替换」落盘 ——
旧实现直接覆盖写入，进程在写一半时退出会留下截断的 JSON，
下次读取时静默返回 ``None``，任务看起来就像凭空消失。
"""

import json
import logging
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StateStore:
    """状态持久化存储（线程安全）。"""

    def __init__(self, storage_path: str = "data/tasks"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _get_file_path(self, task_id: str) -> Path:
        return self.storage_path / f"{task_id}.json"

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态（返回副本，调用方修改不会污染缓存）。"""
        with self._lock:
            cached = self._cache.get(task_id)
            if cached is not None:
                return deepcopy(cached)

            file_path = self._get_file_path(task_id)
            if not file_path.exists():
                return None
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("读取任务状态失败 %s: %s", task_id, exc)
                return None

            self._cache[task_id] = data
            return deepcopy(data)

    def set(self, task_id: str, data: Dict[str, Any]) -> None:
        """保存任务状态。"""
        payload = deepcopy(data)
        with self._lock:
            self._cache[task_id] = payload
            file_path = self._get_file_path(task_id)
            tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, file_path)
            except OSError as exc:
                tmp_path.unlink(missing_ok=True)
                logger.error("保存任务状态失败 %s: %s", task_id, exc)

    def update(self, task_id: str, updates: Dict[str, Any]) -> None:
        """合并更新任务状态。"""
        with self._lock:
            data = self.get(task_id) or {}
            data.update(updates)
            self.set(task_id, data)

    def exists(self, task_id: str) -> bool:
        """检查任务是否存在。"""
        with self._lock:
            if task_id in self._cache:
                return True
            return self._get_file_path(task_id).exists()


# 全局实例（懒加载 + 锁，避免并发首次调用创建两个 store）
_integration_store: Optional[StateStore] = None
_indexing_store: Optional[StateStore] = None
_store_lock = threading.Lock()


def get_integration_store() -> StateStore:
    global _integration_store
    if _integration_store is None:
        with _store_lock:
            if _integration_store is None:
                _integration_store = StateStore("data/tasks/integration")
    return _integration_store


def get_indexing_store() -> StateStore:
    global _indexing_store
    if _indexing_store is None:
        with _store_lock:
            if _indexing_store is None:
                _indexing_store = StateStore("data/tasks/indexing")
    return _indexing_store

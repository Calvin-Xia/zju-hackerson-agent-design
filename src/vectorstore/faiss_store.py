"""向量存储与检索。

设计要点：

* 内存中的 ``_vectors`` 始终是唯一事实来源，FAISS 索引只是加速器；
* 向量与元数据一并落盘，因此 **没有 FAISS 时重启也不会丢数据**
  （旧实现只写 ``index.faiss``，在 numpy 降级模式下重启后检索恒为空）；
* 按 ``chunk_id`` 去重，重复建索引不会产生重复片段；
* 记录嵌入后端指纹，后端变化时拒绝加载旧索引，避免"维度相同但语义不同"
  的脏数据被误用。
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.shared.config import settings

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    """FAISS 向量存储（不可用时自动降级为 numpy 精确检索）。"""

    VECTORS_FILE = "vectors.npy"
    METADATA_FILE = "metadata.json"
    CONFIG_FILE = "config.json"
    INDEX_FILE = "index.faiss"

    def __init__(self, dimension: Optional[int] = None, index_path: Optional[str] = None):
        self.dimension: Optional[int] = dimension
        # VECTOR_DB_PATH 指向向量库根目录，其下按索引名分目录存放
        self.index_path = Path(index_path) if index_path else Path(settings.VECTOR_DB_PATH)
        self.index_path.mkdir(parents=True, exist_ok=True)

        self.index = None
        self.chunk_metadata: List[Dict[str, Any]] = []
        self._vectors: Optional[np.ndarray] = None
        self._backend_signature: Optional[str] = None
        self._lock = threading.RLock()

        if self.dimension:
            self._initialize_index(self.dimension)

    # ------------------------------------------------------------------
    # 索引管理
    # ------------------------------------------------------------------
    def _initialize_index(self, dimension: int) -> None:
        self.dimension = int(dimension)
        try:
            import faiss

            self.index = faiss.IndexFlatIP(self.dimension)
            logger.info("已初始化 FAISS 索引 (dim=%d)", self.dimension)
        except ImportError:
            self.index = None
            logger.info("FAISS 不可用，使用 numpy 精确检索 (dim=%d)", self.dimension)

    def _ensure_dimension(self, vectors: np.ndarray) -> None:
        actual = int(vectors.shape[1])
        if self.dimension is None:
            self._initialize_index(actual)
        elif self.dimension != actual:
            # 维度变化意味着嵌入后端换了：此时已落盘的向量语义不可比，
            # 静默清空会造成"数据莫名消失"，因此直接报错让调用方显式重建。
            raise ValueError(
                f"向量维度不一致（索引 {self.dimension}，新向量 {actual}）。"
                "嵌入后端可能已更换，请先清空并重建向量索引。"
            )

    def _reset(self, clear_metadata: bool = True) -> None:
        if self.dimension:
            self._initialize_index(self.dimension)
        self._vectors = None
        if clear_metadata:
            self.chunk_metadata = []

    def _rebuild_index(self) -> None:
        """根据 ``_vectors`` 重建 FAISS 索引。"""
        if self.index is None or self._vectors is None or len(self._vectors) == 0:
            return
        try:
            import faiss

            self.index = faiss.IndexFlatIP(int(self._vectors.shape[1]))
            self.index.add(np.ascontiguousarray(self._vectors, dtype=np.float32))
        except ImportError:
            self.index = None

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def add_vectors(self, vectors: np.ndarray, metadata: List[Dict[str, Any]]) -> int:
        """添加向量。

        与已有 ``chunk_id`` 重复的条目会被跳过，返回真正新增的数量。
        """
        vectors = np.atleast_2d(np.asarray(vectors, dtype=np.float32))
        if len(vectors) != len(metadata):
            raise ValueError("向量数量与元数据数量不一致")
        if len(vectors) == 0:
            return 0

        with self._lock:
            self._ensure_dimension(vectors)
            normalized = self._normalize(vectors)

            existing_ids = {
                m.get("chunk_id") for m in self.chunk_metadata if m.get("chunk_id")
            }

            kept_vectors: List[np.ndarray] = []
            kept_metadata: List[Dict[str, Any]] = []
            for vector, meta in zip(normalized, metadata):
                chunk_id = meta.get("chunk_id")
                if chunk_id and chunk_id in existing_ids:
                    continue
                kept_vectors.append(vector)
                kept_metadata.append(meta)
                if chunk_id:
                    existing_ids.add(chunk_id)

            if not kept_vectors:
                logger.info("没有新增向量（全部为重复 chunk_id）")
                return 0

            new_vectors = np.vstack(kept_vectors).astype(np.float32)
            if self._vectors is None:
                self._vectors = new_vectors
            else:
                self._vectors = np.vstack([self._vectors, new_vectors]).astype(np.float32)
            self.chunk_metadata.extend(kept_metadata)

            if self.index is not None:
                self.index.add(np.ascontiguousarray(new_vectors))
            logger.info(
                "新增 %d 个向量（跳过 %d 个重复），当前共 %d 个",
                len(kept_vectors),
                len(metadata) - len(kept_vectors),
                len(self.chunk_metadata),
            )
            return len(kept_vectors)

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return (vectors / norms).astype(np.float32)

    def remove_by_textbook(self, textbook_id: str) -> int:
        """删除某本教材的全部片段，返回删除数量。"""
        with self._lock:
            if not self.chunk_metadata:
                return 0
            keep_indices = [
                i for i, m in enumerate(self.chunk_metadata)
                if m.get("textbook_id") != textbook_id
            ]
            removed = len(self.chunk_metadata) - len(keep_indices)
            if removed == 0:
                return 0

            self.chunk_metadata = [self.chunk_metadata[i] for i in keep_indices]
            if self._vectors is not None and len(keep_indices) > 0:
                self._vectors = self._vectors[keep_indices]
            else:
                self._vectors = None
            self._rebuild_index()
            logger.info("删除教材 %s 的 %d 个片段", textbook_id, removed)
            return removed

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def search(self, query_vector: np.ndarray, top_k: int = 5) -> List[Tuple[int, float]]:
        """返回 ``[(index, similarity), ...]``，相似度为余弦相似度。"""
        with self._lock:
            if self._vectors is None or len(self._vectors) == 0:
                return []

            query = np.asarray(query_vector, dtype=np.float32).ravel()
            norm = float(np.linalg.norm(query))
            if norm == 0:
                return []
            query = (query / norm).reshape(1, -1)

            if self.index is not None and self.index.ntotal == len(self._vectors):
                k = min(top_k, self.index.ntotal)
                similarities, indices = self.index.search(
                    np.ascontiguousarray(query, dtype=np.float32), k
                )
                return [
                    (int(idx), float(sim))
                    for idx, sim in zip(indices[0], similarities[0])
                    if idx >= 0
                ]

            # numpy 精确检索（FAISS 缺失或索引与数据不同步时）
            similarities = (self._vectors @ query.T).ravel()
            k = min(top_k, len(similarities))
            top_indices = np.argpartition(-similarities, k - 1)[:k]
            top_indices = top_indices[np.argsort(-similarities[top_indices])]
            return [(int(idx), float(similarities[idx])) for idx in top_indices]

    def get_metadata(self, index: int) -> Optional[Dict[str, Any]]:
        if 0 <= index < len(self.chunk_metadata):
            return self.chunk_metadata[index]
        return None

    def set_embedding_signature(self, signature: Optional[str]) -> None:
        """记录当前嵌入后端指纹，随索引一起落盘。"""
        self._backend_signature = signature

    @property
    def embedding_signature(self) -> Optional[str]:
        return self._backend_signature

    @property
    def size(self) -> int:
        return len(self.chunk_metadata)

    def indexed_textbook_ids(self) -> List[str]:
        return sorted({m.get("textbook_id", "") for m in self.chunk_metadata if m.get("textbook_id")})

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def save(self, name: str = "default") -> None:
        """把向量与元数据落盘。

        ``vectors.npy`` 是唯一权威数据，FAISS 索引在加载时按需重建，
        因此不额外持久化 ``index.faiss``（避免两处数据不一致）。
        """
        save_dir = self.index_path / name
        save_dir.mkdir(parents=True, exist_ok=True)

        with self._lock:
            vectors_file = save_dir / self.VECTORS_FILE
            if self._vectors is not None and len(self._vectors) > 0:
                np.save(vectors_file, self._vectors)
            elif vectors_file.exists():
                vectors_file.unlink()

            with open(save_dir / self.METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.chunk_metadata, f, ensure_ascii=False, indent=2)

            stale_index = save_dir / self.INDEX_FILE
            if stale_index.exists():
                stale_index.unlink()

            config = {
                "dimension": self.dimension,
                "total_vectors": len(self.chunk_metadata),
                "embedding_signature": self._backend_signature,
                "version": 2,
            }
            with open(save_dir / self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info("已保存索引 '%s'（%d 个向量）", name, len(self.chunk_metadata))

    def load(self, name: str = "default", expected_signature: Optional[str] = None) -> bool:
        """加载索引。

        ``expected_signature`` 与落盘指纹不一致时返回 ``False``，
        调用方应重新建立索引。
        """
        load_dir = self.index_path / name
        if not load_dir.exists():
            logger.info("索引 '%s' 不存在", name)
            return False

        with self._lock:
            try:
                config: Dict[str, Any] = {}
                config_file = load_dir / self.CONFIG_FILE
                if config_file.exists():
                    with open(config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)

                stored_signature = config.get("embedding_signature")
                if expected_signature and not stored_signature:
                    logger.warning(
                        "索引 '%s' 缺少嵌入后端指纹，无法确认与当前后端兼容，跳过加载", name
                    )
                    return False
                if stored_signature and not expected_signature:
                    logger.warning(
                        "索引 '%s' 未指定期望的嵌入后端，跳过加载以规避脏数据", name
                    )
                    return False
                if (
                    expected_signature
                    and stored_signature
                    and stored_signature != expected_signature
                ):
                    logger.warning(
                        "索引 '%s' 的嵌入后端已变化（%s -> %s），需要重新建立索引",
                        name,
                        stored_signature,
                        expected_signature,
                    )
                    return False

                metadata_file = load_dir / self.METADATA_FILE
                vectors_file = load_dir / self.VECTORS_FILE
                if not metadata_file.exists() or not vectors_file.exists():
                    logger.warning(
                        "索引 '%s' 不完整（缺少 %s），需要重新建立索引",
                        name,
                        self.VECTORS_FILE if metadata_file.exists() else self.METADATA_FILE,
                    )
                    return False

                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                vectors = np.load(vectors_file).astype(np.float32)
                vectors = np.atleast_2d(vectors) if vectors.size else vectors.reshape(0, 0)

                if len(vectors) != len(metadata):
                    logger.warning(
                        "索引 '%s' 向量数(%d)与元数据数(%d)不一致，忽略",
                        name,
                        len(vectors),
                        len(metadata),
                    )
                    return False

                self.chunk_metadata = metadata
                self._vectors = vectors if len(vectors) else None
                self._backend_signature = stored_signature
                if len(vectors):
                    self._initialize_index(int(vectors.shape[1]))
                    self._rebuild_index()
                else:
                    self._reset(clear_metadata=False)

                logger.info("已加载索引 '%s'（%d 个向量）", name, len(self.chunk_metadata))
                return True
            except Exception as exc:
                logger.error("加载索引失败: %s", exc)
                self._reset(clear_metadata=True)
                return False

    def clear(self, purge: bool = False, name: str = "default") -> None:
        """清空内存索引；``purge=True`` 时同时删除磁盘文件。"""
        with self._lock:
            self._reset(clear_metadata=True)
            self._backend_signature = None
            if purge:
                save_dir = self.index_path / name
                for filename in (self.VECTORS_FILE, self.METADATA_FILE,
                                 self.CONFIG_FILE, self.INDEX_FILE):
                    path = save_dir / filename
                    if path.exists():
                        path.unlink()
        logger.info("已清空向量存储")


_vector_store: Optional[FAISSVectorStore] = None
_vector_store_lock = threading.Lock()


def get_vector_store(dimension: Optional[int] = None) -> FAISSVectorStore:
    """获取向量存储单例。"""
    global _vector_store
    if _vector_store is None:
        with _vector_store_lock:
            if _vector_store is None:
                _vector_store = FAISSVectorStore(dimension=dimension)
    return _vector_store


def reset_vector_store() -> None:
    """重置单例（测试用）。"""
    global _vector_store
    with _vector_store_lock:
        _vector_store = None

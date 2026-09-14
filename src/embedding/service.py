"""文本向量化服务。

提供两种后端：

1. ``sentence-transformers`` —— 首选，语义质量最好；
2. ``hashing`` —— 无状态降级方案（离线环境 / 模型不可用时自动启用）。

降级方案使用 ``HashingVectorizer`` 对字符 n-gram 做哈希投影，**无需 fit**，
因此索引期与查询期的向量严格一致，服务重启后也不会漂移 —— 这是旧版
TF-IDF 降级方案（在首批文本上 fit）无法保证的。

向量一律做 L2 归一化，余弦相似度即内积。
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from src.shared.config import settings

logger = logging.getLogger(__name__)

EmbeddingInput = Union[str, Sequence[str]]


class EmbeddingService:
    """文本嵌入服务（线程安全单例使用）。"""

    def __init__(
        self,
        model_name: Optional[str] = None,
        cache_dir: Optional[str] = None,
        backend: Optional[str] = None,
    ):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.requested_backend = (backend or settings.EMBEDDING_BACKEND or "auto").lower()
        self.cache_dir = Path(cache_dir) if cache_dir else Path("data/embedding_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.model = None
        self._backend: Optional[str] = None
        self._dimension: int = int(settings.EMBEDDING_DIM)
        self._cache: Dict[str, np.ndarray] = {}
        self._dirty_count = 0
        self._save_threshold = 64
        self._lock = threading.RLock()
        self._ready = False

    # ------------------------------------------------------------------
    # 后端与元信息
    # ------------------------------------------------------------------
    def _load_model(self) -> None:
        """惰性初始化后端（只执行一次）。"""
        if self._ready:
            return

        with self._lock:
            if self._ready:
                return

            if self.requested_backend in ("auto", "sentence-transformers"):
                if self._try_load_sentence_transformer():
                    self._backend = "sentence-transformers"
                elif self.requested_backend == "sentence-transformers":
                    logger.warning("sentence-transformers 不可用，降级为 hashing 后端")
            elif self.requested_backend not in ("hashing",):
                logger.warning(
                    "未知的 EMBEDDING_BACKEND=%r，按 auto 处理",
                    self.requested_backend,
                )

            if self._backend is None:
                self._load_hashing_backend()

            self._ready = True
            self._load_cache()
            logger.info(
                "嵌入后端就绪: backend=%s, dimension=%d, signature=%s",
                self._backend,
                self._dimension,
                self.signature,
            )

    def _try_load_sentence_transformer(self) -> bool:
        if settings.EMBEDDING_OFFLINE:
            # 关闭 HuggingFace 的网络探测，避免离线环境下长达数分钟的重试
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning("未安装 sentence-transformers，使用 hashing 后端")
            return False

        try:
            logger.info("加载嵌入模型: %s", self.model_name)
            model = SentenceTransformer(self.model_name, local_files_only=True)
        except Exception as exc:  # 模型缺失 / 无网络 / 权重损坏
            logger.warning("本地加载嵌入模型失败(%s)，使用 hashing 后端: %s", self.model_name, exc)
            return False

        try:
            dim = int(model.get_sentence_embedding_dimension())
        except Exception:
            dim = int(settings.EMBEDDING_DIM)
        if dim <= 0:
            logger.warning("嵌入模型维度非法(%s)，使用 hashing 后端", dim)
            return False

        self.model = model
        self._dimension = dim
        return True

    def _load_hashing_backend(self) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer

        self._dimension = int(settings.EMBEDDING_DIM)
        # 字符 n-gram（含单字）对中文无需分词，对英文术语同样有效；
        # alternate_sign=True 让哈希投影近似 SimHash，余弦相似度更稳定。
        self.model = HashingVectorizer(
            analyzer="char",
            ngram_range=(1, 3),
            n_features=self._dimension,
            alternate_sign=True,
            norm="l2",
            dtype=np.float32,
        )
        self._backend = "hashing"
        logger.info("使用 hashing 降级嵌入后端 (dim=%d, char 1-3 gram)", self._dimension)

    @property
    def backend(self) -> str:
        self._load_model()
        return self._backend or "hashing"

    @property
    def dimension(self) -> int:
        self._load_model()
        return self._dimension

    @property
    def signature(self) -> str:
        """后端指纹，用于判断已落盘的向量是否仍然有效。"""
        self._load_model()
        if self._backend == "sentence-transformers":
            return f"st:{self.model_name}:{self._dimension}"
        return f"hashing:char1-3:{self._dimension}"

    @property
    def suggested_min_score(self) -> float:
        """该后端下「相关」的推荐相似度下限。

        两种后端的余弦分布差异很大（语义模型普遍偏高，哈希投影偏低），
        按后端给出不同的默认阈值，避免降级运行时召回为空。
        """
        self._load_model()
        return 0.35 if self._backend == "sentence-transformers" else 0.18

    # ------------------------------------------------------------------
    # 缓存
    # ------------------------------------------------------------------
    def _cache_file(self) -> Path:
        digest = hashlib.md5(self.signature.encode("utf-8")).hexdigest()[:10]
        return self.cache_dir / f"embedding_cache_{digest}.npz"

    def _load_cache(self) -> None:
        path = self._cache_file()
        if not path.exists():
            return
        try:
            with np.load(path, allow_pickle=False) as data:
                keys = [str(k) for k in data["keys"]]
                vectors = data["vectors"]
                stored_signature = str(data["signature"]) if "signature" in data else ""
            if stored_signature != self.signature:
                logger.warning("嵌入缓存指纹不匹配，忽略旧缓存: %s", path)
                return
            for key, vector in zip(keys, vectors):
                self._cache[key] = vector.astype(np.float32, copy=False)
            logger.info("加载嵌入缓存 %d 条 (%s)", len(self._cache), path.name)
        except Exception as exc:
            logger.warning("加载嵌入缓存失败: %s", exc)

    def _save_cache(self) -> None:
        if not self._cache:
            return
        path = self._cache_file()
        try:
            keys = list(self._cache.keys())
            vectors = np.vstack([self._cache[k] for k in keys]).astype(np.float32)
            np.savez_compressed(
                path,
                keys=np.array(keys, dtype=str),  # 固定宽度字符串，避免依赖 pickle
                vectors=vectors,
                signature=np.array(self.signature),
            )
            logger.debug("保存嵌入缓存 %d 条 -> %s", len(keys), path.name)
        except Exception as exc:
            logger.warning("保存嵌入缓存失败: %s", exc)

    # ------------------------------------------------------------------
    # 编码
    # ------------------------------------------------------------------
    def _encode_uncached(self, texts: List[str]) -> np.ndarray:
        if self._backend == "sentence-transformers":
            return np.asarray(
                self.model.encode(
                    texts,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    batch_size=32,
                ),
                dtype=np.float32,
            )
        matrix = self.model.transform(texts)
        matrix = np.asarray(matrix.todense() if hasattr(matrix, "todense") else matrix, dtype=np.float32)
        return self._l2_normalize(matrix)

    @staticmethod
    def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return (matrix / norms).astype(np.float32)

    def encode(self, texts: EmbeddingInput) -> np.ndarray:
        """把文本编码成 L2 归一化的向量。

        单个字符串返回 ``(dim,)``，列表返回 ``(n, dim)``。

        缓存命中在锁内完成；真正的模型推理在锁外执行，
        避免并发调用被串行化（推理是最耗时的部分）。
        """
        self._load_model()

        single_input = isinstance(texts, str)
        text_list: List[str] = [texts] if single_input else list(texts)

        if not text_list:
            return np.zeros((0, self._dimension), dtype=np.float32)

        results: List[Optional[np.ndarray]] = [None] * len(text_list)

        # 第一步：只读缓存（持锁时间极短）
        with self._lock:
            miss_indices: set = set()
            for i, text in enumerate(text_list):
                cached = self._cache.get(self._cache_key(text))
                if cached is None:
                    miss_indices.add(i)
                else:
                    results[i] = cached
            misses: List[Tuple[int, str]] = [
                (i, text) for i, text in enumerate(text_list) if i in miss_indices
            ]

        # 第二步：锁外做批量推理
        if misses:
            logger.info("编码 %d 条未缓存文本", len(misses))
            new_embeddings = self._encode_uncached([text for _, text in misses])

            # 第三步：写回缓存（另一线程可能已写入相同 key，保留先写入的结果）
            with self._lock:
                for (index, text), embedding in zip(misses, new_embeddings):
                    key = self._cache_key(text)
                    cached = self._cache.get(key)
                    if cached is None:
                        cached = embedding.astype(np.float32, copy=False)
                        self._cache[key] = cached
                        self._dirty_count += 1
                    results[index] = cached

                if self._dirty_count >= self._save_threshold:
                    self._save_cache()
                    self._dirty_count = 0

        array = np.vstack([r for r in results if r is not None]).astype(np.float32)
        if array.shape[1] != self._dimension:
            raise ValueError(
                f"嵌入维度不一致: 期望 {self._dimension}, 实际 {array.shape[1]}"
            )
        if single_input:
            return array[0]
        return array

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # 相似度
    # ------------------------------------------------------------------
    def similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """两个向量的余弦相似度。"""
        vec1 = np.asarray(vec1, dtype=np.float32).ravel()
        vec2 = np.asarray(vec2, dtype=np.float32).ravel()
        norm1 = float(np.linalg.norm(vec1))
        norm2 = float(np.linalg.norm(vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def batch_similarity(self, vectors1: np.ndarray, vectors2: np.ndarray) -> np.ndarray:
        """批量余弦相似度矩阵 ``(n, m)``。"""
        matrix1 = np.atleast_2d(np.asarray(vectors1, dtype=np.float32))
        matrix2 = np.atleast_2d(np.asarray(vectors2, dtype=np.float32))
        if matrix1.shape[1] != matrix2.shape[1]:
            raise ValueError("两组向量维度不一致")
        norm1 = np.where(np.linalg.norm(matrix1, axis=1, keepdims=True) == 0, 1.0,
                         np.linalg.norm(matrix1, axis=1, keepdims=True))
        norm2 = np.where(np.linalg.norm(matrix2, axis=1, keepdims=True) == 0, 1.0,
                         np.linalg.norm(matrix2, axis=1, keepdims=True))
        return (matrix1 / norm1) @ (matrix2 / norm2).T

    def flush(self) -> None:
        """把缓存落盘（进程退出/索引完成后调用）。"""
        with self._lock:
            if self._dirty_count:
                self._save_cache()
                self._dirty_count = 0

    def clear_cache(self) -> None:
        """清空当前后端的嵌入缓存。"""
        with self._lock:
            self._cache.clear()
            self._dirty_count = 0
            path = self._cache_file()
            if path.exists():
                path.unlink()
            logger.info("嵌入缓存已清空")


_embedding_service: Optional[EmbeddingService] = None
_embedding_lock = threading.Lock()


def get_embedding_service(model_name: Optional[str] = None) -> EmbeddingService:
    """获取嵌入服务单例。"""
    global _embedding_service
    if _embedding_service is None:
        with _embedding_lock:
            if _embedding_service is None:
                _embedding_service = EmbeddingService(model_name=model_name)
    return _embedding_service


def reset_embedding_service() -> None:
    """重置单例（测试用）。"""
    global _embedding_service
    with _embedding_lock:
        _embedding_service = None

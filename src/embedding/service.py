"""
共享嵌入服务模块

提供文本向量化功能，支持：
- 模型加载和初始化
- 单个和批量文本编码
- 向量缓存
- 相似度计算
"""

import hashlib
import logging
from typing import List, Optional, Union
import numpy as np
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class EmbeddingService:
    """文本嵌入服务"""
    
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2", cache_dir: Optional[str] = None):
        """
        初始化嵌入服务
        
        Args:
            model_name: 嵌入模型名称
            cache_dir: 缓存目录路径
        """
        self.model_name = model_name
        self.model = None
        self.cache_dir = Path(cache_dir) if cache_dir else Path("data/embedding_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, np.ndarray] = {}
        self._dirty_count = 0
        self._save_threshold = 10  # 每10次更新保存一次
        self._load_cache()
    
    def _load_cache(self):
        """从磁盘加载缓存"""
        cache_file = self.cache_dir / "embedding_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for key, vector_list in data.items():
                    self._cache[key] = np.array(vector_list, dtype=np.float32)
                logger.info(f"Loaded {len(self._cache)} cached embeddings")
            except Exception as e:
                logger.warning(f"Failed to load embedding cache: {e}")
    
    def _save_cache(self):
        """保存缓存到磁盘"""
        cache_file = self.cache_dir / "embedding_cache.json"
        try:
            data = {key: vector.tolist() for key, vector in self._cache.items()}
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            logger.debug(f"Saved {len(self._cache)} embeddings to cache")
        except Exception as e:
            logger.warning(f"Failed to save embedding cache: {e}")
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _load_model(self):
        """懒加载模型"""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading embedding model: {self.model_name}")
                self.model = SentenceTransformer(self.model_name)
                logger.info("Embedding model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise
    
    def encode(self, texts: Union[str, List[str]], show_progress: bool = False) -> np.ndarray:
        """
        将文本编码为向量
        
        Args:
            texts: 单个文本或文本列表
            show_progress: 是否显示进度
            
        Returns:
            向量或向量数组
        """
        self._load_model()
        
        single_input = isinstance(texts, str)
        if single_input:
            texts = [texts]
        
        # 检查缓存
        results = []
        uncached_texts = []
        uncached_indices = []
        
        for i, text in enumerate(texts):
            cache_key = self._get_cache_key(text)
            if cache_key in self._cache:
                results.append(self._cache[cache_key])
            else:
                results.append(None)
                uncached_texts.append(text)
                uncached_indices.append(i)
        
        # 编码未缓存的文本
        if uncached_texts:
            logger.info(f"Encoding {len(uncached_texts)} uncached texts")
            new_embeddings = self.model.encode(
                uncached_texts,
                show_progress_bar=show_progress,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            
            # 更新缓存
            for idx, text, embedding in zip(uncached_indices, uncached_texts, new_embeddings):
                cache_key = self._get_cache_key(text)
                self._cache[cache_key] = embedding
                results[idx] = embedding
                self._dirty_count += 1
            
            # 批量保存缓存
            if self._dirty_count >= self._save_threshold:
                self._save_cache()
                self._dirty_count = 0
        
        results_array = np.array(results, dtype=np.float32)
        
        if single_input:
            return results_array[0]
        return results_array
    
    def similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        计算两个向量的余弦相似度
        
        Args:
            vec1: 向量1
            vec2: 向量2
            
        Returns:
            相似度分数 (0-1)
        """
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def batch_similarity(self, vectors1: np.ndarray, vectors2: np.ndarray) -> np.ndarray:
        """
        批量计算相似度矩阵
        
        Args:
            vectors1: 向量矩阵1 (n, d)
            vectors2: 向量矩阵2 (m, d)
            
        Returns:
            相似度矩阵 (n, m)
        """
        # 归一化
        norms1 = np.linalg.norm(vectors1, axis=1, keepdims=True)
        norms2 = np.linalg.norm(vectors2, axis=1, keepdims=True)
        
        # 避免除零
        norms1 = np.where(norms1 == 0, 1, norms1)
        norms2 = np.where(norms2 == 0, 1, norms2)
        
        normalized1 = vectors1 / norms1
        normalized2 = vectors2 / norms2
        
        # 计算余弦相似度矩阵
        return np.dot(normalized1, normalized2.T)
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        cache_file = self.cache_dir / "embedding_cache.json"
        if cache_file.exists():
            cache_file.unlink()
        logger.info("Embedding cache cleared")


# 全局单例
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service(model_name: str = "paraphrase-multilingual-MiniLM-L12-v2") -> EmbeddingService:
    """获取嵌入服务单例"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(model_name=model_name)
    return _embedding_service

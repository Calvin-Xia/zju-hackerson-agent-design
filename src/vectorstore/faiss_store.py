"""
FAISS向量存储模块

实现向量存储和检索功能：
- 向量索引
- 语义检索
- 持久化存储
"""

import logging
import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    """FAISS向量存储"""
    
    def __init__(self, dimension: int = 384, index_path: Optional[str] = None):
        """
        初始化向量存储
        
        Args:
            dimension: 向量维度
            index_path: 索引存储路径
        """
        self.dimension = dimension
        self.index_path = Path(index_path) if index_path else Path("data/vectorstore")
        self.index_path.mkdir(parents=True, exist_ok=True)
        
        self.index = None
        self.chunk_metadata: List[Dict[str, Any]] = []
        self._initialize_index()
    
    def _initialize_index(self):
        """初始化FAISS索引"""
        try:
            import faiss
            self.index = faiss.IndexFlatIP(self.dimension)
            logger.info(f"Initialized FAISS index with dimension {self.dimension}")
        except ImportError:
            logger.warning("FAISS not available, using numpy fallback")
            self.index = None
    
    def add_vectors(self, vectors: np.ndarray, metadata: List[Dict[str, Any]]):
        """
        添加向量到索引
        
        Args:
            vectors: 向量数组 (n, dimension)
            metadata: 元数据列表
        """
        if len(vectors) != len(metadata):
            raise ValueError("Vectors and metadata must have same length")
        
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        normalized_vectors = vectors / norms
        
        if self.index is not None:
            self.index.add(normalized_vectors.astype(np.float32))
        else:
            if not hasattr(self, '_vectors'):
                self._vectors = normalized_vectors
            else:
                self._vectors = np.vstack([self._vectors, normalized_vectors])
        
        self.chunk_metadata.extend(metadata)
        logger.info(f"Added {len(vectors)} vectors to index")
    
    def search(self, query_vector: np.ndarray, top_k: int = 5) -> List[Tuple[int, float]]:
        """
        搜索最相似的向量
        
        Args:
            query_vector: 查询向量
            top_k: 返回数量
            
        Returns:
            [(index, similarity), ...]
        """
        query_norm = np.linalg.norm(query_vector)
        if query_norm > 0:
            query_vector = query_vector / query_norm
        
        query_vector = query_vector.reshape(1, -1).astype(np.float32)
        
        if self.index is not None:
            similarities, indices = self.index.search(query_vector, min(top_k, self.index.ntotal))
            results = [(int(idx), float(sim)) for idx, sim in zip(indices[0], similarities[0]) if idx >= 0]
        else:
            if not hasattr(self, '_vectors') or len(self._vectors) == 0:
                return []
            
            similarities = np.dot(self._vectors, query_vector.T).flatten()
            top_indices = np.argsort(similarities)[::-1][:top_k]
            results = [(int(idx), float(similarities[idx])) for idx in top_indices]
        
        return results
    
    def get_metadata(self, index: int) -> Optional[Dict[str, Any]]:
        """获取元数据"""
        if 0 <= index < len(self.chunk_metadata):
            return self.chunk_metadata[index]
        return None
    
    def save(self, name: str = "default"):
        """保存索引到磁盘"""
        save_dir = self.index_path / name
        save_dir.mkdir(parents=True, exist_ok=True)
        
        if self.index is not None:
            import faiss
            faiss.write_index(self.index, str(save_dir / "index.faiss"))
        
        with open(save_dir / "metadata.json", 'w', encoding='utf-8') as f:
            json.dump(self.chunk_metadata, f, ensure_ascii=False, indent=2)
        
        config = {
            "dimension": self.dimension,
            "total_vectors": len(self.chunk_metadata)
        }
        with open(save_dir / "config.json", 'w', encoding='utf-8') as f:
            json.dump(config, f)
        
        logger.info(f"Saved index '{name}' with {len(self.chunk_metadata)} vectors")
    
    def load(self, name: str = "default") -> bool:
        """从磁盘加载索引"""
        load_dir = self.index_path / name
        
        if not load_dir.exists():
            logger.warning(f"Index '{name}' not found")
            return False
        
        try:
            config_file = load_dir / "config.json"
            if config_file.exists():
                with open(config_file, 'r') as f:
                    config = json.load(f)
                self.dimension = config.get("dimension", self.dimension)
            
            index_file = load_dir / "index.faiss"
            if index_file.exists():
                import faiss
                self.index = faiss.read_index(str(index_file))
            
            metadata_file = load_dir / "metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    self.chunk_metadata = json.load(f)
            
            logger.info(f"Loaded index '{name}' with {len(self.chunk_metadata)} vectors")
            return True
        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return False
    
    def clear(self):
        """清空索引"""
        self._initialize_index()
        self.chunk_metadata = []
        logger.info("Cleared vector store")


_vector_store: Optional[FAISSVectorStore] = None


def get_vector_store(dimension: int = 384) -> FAISSVectorStore:
    """获取向量存储单例"""
    global _vector_store
    if _vector_store is None:
        _vector_store = FAISSVectorStore(dimension=dimension)
    return _vector_store

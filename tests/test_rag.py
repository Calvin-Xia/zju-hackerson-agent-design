"""
RAG模块测试

测试文档分块、向量存储、问答功能
"""

import pytest
import numpy as np
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.rag.chunking import TextChunker, DocumentChunk
from src.vectorstore.faiss_store import FAISSVectorStore
from src.models.textbook import Textbook, Chapter


@pytest.fixture
def sample_textbook():
    return Textbook(
        textbook_id="test_book",
        filename="test.pdf",
        title="测试教材",
        chapters=[
            Chapter(
                chapter_id="ch1",
                title="第一章 基础概念",
                content="这是第一章的内容。" * 50,
                page_start=1
            ),
            Chapter(
                chapter_id="ch2",
                title="第二章 高级概念",
                content="这是第二章的内容。" * 50,
                page_start=20
            ),
        ]
    )


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d)


class TestTextChunker:
    """文本分块器测试"""
    
    def test_chunk_short_text(self):
        chunker = TextChunker(chunk_size=100, chunk_overlap=20)
        text = "这是一段短文本。"
        chunks = chunker.chunk_text(text)
        
        assert len(chunks) == 1
        assert chunks[0] == text
    
    def test_chunk_long_text(self):
        chunker = TextChunker(chunk_size=50, chunk_overlap=10)
        text = "这是一段很长的文本。" * 20
        chunks = chunker.chunk_text(text)
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 60
    
    def test_chunk_chapter(self, sample_textbook):
        chunker = TextChunker(chunk_size=200, chunk_overlap=50)
        chapter = sample_textbook.chapters[0]
        
        chunks = chunker.chunk_chapter(sample_textbook, chapter)
        
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, DocumentChunk)
            assert chunk.textbook_id == "test_book"
            assert chunk.chapter_id == "ch1"
            assert chunk.char_count > 0
    
    def test_chunk_textbook(self, sample_textbook):
        chunker = TextChunker(chunk_size=200, chunk_overlap=50)
        chunks = chunker.chunk_textbook(sample_textbook)
        
        assert len(chunks) > 0
        
        chapters = set(chunk.chapter_id for chunk in chunks)
        assert "ch1" in chapters
        assert "ch2" in chapters


class TestFAISSVectorStore:
    """FAISS向量存储测试"""
    
    def test_add_and_search(self, temp_dir):
        store = FAISSVectorStore(dimension=128, index_path=str(temp_dir))
        
        vectors = np.random.rand(10, 128).astype(np.float32)
        metadata = [{"id": i, "text": f"chunk_{i}"} for i in range(10)]
        
        store.add_vectors(vectors, metadata)
        
        query = np.random.rand(128).astype(np.float32)
        results = store.search(query, top_k=3)
        
        assert len(results) == 3
        for idx, similarity in results:
            assert 0 <= idx < 10
            assert -1 <= similarity <= 1
    
    def test_save_and_load(self, temp_dir):
        store = FAISSVectorStore(dimension=128, index_path=str(temp_dir))
        
        vectors = np.random.rand(5, 128).astype(np.float32)
        metadata = [{"id": i} for i in range(5)]
        store.add_vectors(vectors, metadata)
        
        store.save("test_index")
        
        new_store = FAISSVectorStore(dimension=128, index_path=str(temp_dir))
        success = new_store.load("test_index")
        
        assert success is True
        assert len(new_store.chunk_metadata) == 5
    
    def test_clear(self, temp_dir):
        store = FAISSVectorStore(dimension=128, index_path=str(temp_dir))
        
        vectors = np.random.rand(5, 128).astype(np.float32)
        metadata = [{"id": i} for i in range(5)]
        store.add_vectors(vectors, metadata)
        
        store.clear()
        
        assert len(store.chunk_metadata) == 0


class TestDocumentChunk:
    """文档块测试"""
    
    def test_to_dict(self):
        chunk = DocumentChunk(
            chunk_id="test_chunk_1",
            content="测试内容",
            textbook_id="book_1",
            textbook_title="测试教材",
            chapter_id="ch1",
            chapter_title="第一章",
            page_start=1,
            chunk_index=0,
            char_count=4
        )
        
        data = chunk.to_dict()
        
        assert data["chunk_id"] == "test_chunk_1"
        assert data["content"] == "测试内容"
        assert data["textbook_id"] == "book_1"
        assert data["char_count"] == 4


class TestRAGAPI:
    """RAG API测试"""
    
    def test_index_request_validation(self):
        from src.api.routes.rag import IndexRequest
        
        request = IndexRequest(file_ids=["file_1", "file_2"])
        assert len(request.file_ids) == 2
    
    def test_query_request_validation(self):
        from src.api.routes.rag import QueryRequest
        
        request = QueryRequest(question="什么是炎症？")
        assert request.question == "什么是炎症？"
    
    def test_index_status_model(self):
        from src.api.routes.rag import IndexStatus
        
        status = IndexStatus(
            total_chunks=100,
            indexed_textbooks=3,
            is_ready=True
        )
        assert status.total_chunks == 100
        assert status.is_ready is True

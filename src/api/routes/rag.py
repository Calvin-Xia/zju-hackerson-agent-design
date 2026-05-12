"""
RAG API端点模块

提供RAG问答的REST API：
- POST /index - 建立向量索引
- POST /query - 提问
- GET /status - 查询索引状态
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from src.rag.chunking import TextChunker, DocumentChunk
from src.embedding.service import get_embedding_service
from src.vectorstore.faiss_store import get_vector_store
from src.rag.qa import get_qa_instance, QAResponse
from src.parsers.factory import parse_file
from src.shared.config import settings
from src.shared.state_store import get_indexing_store

logger = logging.getLogger(__name__)

router = APIRouter()

state_store = get_indexing_store()


class IndexRequest(BaseModel):
    file_ids: List[str]


class IndexResponse(BaseModel):
    task_id: str
    message: str


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]]
    source_chunks: List[str]


class IndexStatus(BaseModel):
    total_chunks: int
    indexed_textbooks: int
    is_ready: bool


async def _index_files(task_id: str, file_ids: List[str]):
    """异步建立索引"""
    try:
        state_store.set(task_id, {
            "status": "processing",
            "progress": 0.0,
            "error_message": None
        })
        
        chunker = TextChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP
        )
        
        embedding_service = get_embedding_service()
        vector_store = get_vector_store()
        vector_store.clear()
        
        all_chunks: List[DocumentChunk] = []
        
        for i, file_id in enumerate(file_ids):
            parsed_path = Path("data/textbooks") / f"{file_id}_parsed.json"
            if not parsed_path.exists():
                logger.warning(f"Parsed file not found: {file_id}")
                continue
            
            with open(parsed_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            from src.models.textbook import Textbook
            textbook = Textbook.model_validate(data)
            
            chunks = chunker.chunk_textbook(textbook)
            all_chunks.extend(chunks)
            
            state_store.update(task_id, {"progress": (i + 1) / len(file_ids) * 50})
        
        if not all_chunks:
            raise ValueError("No valid chunks generated")
        
        texts = [chunk.content for chunk in all_chunks]
        embeddings = embedding_service.encode(texts, show_progress=True)
        
        metadata = [chunk.to_dict() for chunk in all_chunks]
        vector_store.add_vectors(embeddings, metadata)
        
        vector_store.save("default")
        
        state_store.set(task_id, {
            "status": "completed",
            "progress": 100.0,
            "error_message": None,
            "total_chunks": len(all_chunks),
            "indexed_textbooks": len(file_ids)
        })
        
        logger.info(f"Indexing completed: {len(all_chunks)} chunks from {len(file_ids)} textbooks")
        
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        state_store.update(task_id, {
            "status": "failed",
            "progress": 0.0,
            "error_message": str(e)
        })


@router.post("/index", response_model=IndexResponse)
async def create_index(request: IndexRequest, background_tasks: BackgroundTasks):
    """建立向量索引"""
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="No file IDs provided")
    
    for file_id in request.file_ids:
        parsed_path = Path("data/textbooks") / f"{file_id}_parsed.json"
        if not parsed_path.exists():
            raise HTTPException(status_code=404, detail=f"Parsed file not found: {file_id}")
    
    task_id = f"index_{uuid.uuid4().hex[:8]}"
    
    background_tasks.add_task(_index_files, task_id, request.file_ids)
    
    return IndexResponse(
        task_id=task_id,
        message=f"Indexing started for {len(request.file_ids)} files"
    )


@router.post("/query", response_model=QueryResponse)
async def query_knowledge(request: QueryRequest):
    """提问"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    vector_store = get_vector_store()
    if len(vector_store.chunk_metadata) == 0:
        raise HTTPException(status_code=400, detail="Knowledge base is empty. Please index textbooks first.")
    
    qa = get_qa_instance(top_k=settings.TOP_K)
    response = await qa.answer_question(request.question)
    
    return QueryResponse(
        answer=response.answer,
        citations=[c.to_dict() for c in response.citations],
        source_chunks=response.source_chunks
    )


@router.get("/status", response_model=IndexStatus)
async def get_index_status():
    """获取索引状态"""
    vector_store = get_vector_store()
    
    return IndexStatus(
        total_chunks=len(vector_store.chunk_metadata),
        indexed_textbooks=len(set(
            m.get("textbook_id", "") for m in vector_store.chunk_metadata
        )),
        is_ready=len(vector_store.chunk_metadata) > 0
    )


@router.delete("/index")
async def clear_index():
    """清空索引"""
    vector_store = get_vector_store()
    vector_store.clear()
    return {"message": "Index cleared successfully"}

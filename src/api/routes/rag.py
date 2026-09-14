"""RAG 索引与问答 API。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from src.api.routes.parse import normalize_textbook
from src.embedding.service import get_embedding_service
from src.models.textbook import Textbook
from src.rag.chunking import DocumentChunk, TextChunker
from src.rag.qa import NO_ANSWER_TEXT, get_qa_instance
from src.shared.config import settings
from src.shared.state_store import get_indexing_store
from src.vectorstore.faiss_store import get_vector_store

logger = logging.getLogger(__name__)

router = APIRouter()

state_store = get_indexing_store()


class IndexRequest(BaseModel):
    file_ids: List[str] = Field(..., min_length=1)


class IndexResponse(BaseModel):
    task_id: str
    message: str


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)


class QueryResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]]
    source_chunks: List[str]
    retrieved_count: int = 0
    top_score: float = 0.0


class IndexStatus(BaseModel):
    total_chunks: int
    indexed_textbooks: int
    is_ready: bool
    textbook_ids: List[str] = []
    embedding_backend: str = ""
    dimension: int = 0


class IndexTaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    message: Optional[str] = None
    error_message: Optional[str] = None
    total_chunks: int = 0


def _load_textbook(file_id: str) -> Optional[Textbook]:
    """读取解析结果（在子线程中调用）。"""
    parsed_path = settings.textbooks_dir / f"{file_id}_parsed.json"
    if not parsed_path.exists():
        return None
    try:
        with open(parsed_path, "r", encoding="utf-8") as f:
            textbook = Textbook.model_validate(json.load(f))
        # 以路由层的 file_id 为准，保证向量元数据与文件列表一致
        # （历史解析结果里 textbook_id / 标题可能残留存储文件名）
        return normalize_textbook(textbook, file_id)
    except Exception as exc:
        logger.error("加载解析结果失败 %s: %s", file_id, exc)
        return None


async def _index_files(task_id: str, file_ids: List[str]) -> None:
    """建立向量索引（后台任务）。"""
    try:
        state_store.set(task_id, {
            "status": "processing",
            "progress": 0.0,
            "message": "读取解析结果",
            "error_message": None,
            "total_chunks": 0,
        })

        chunker = TextChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
        embedding_service = get_embedding_service()
        vector_store = get_vector_store()

        all_chunks: List[DocumentChunk] = []
        indexed_ids: List[str] = []

        for position, file_id in enumerate(file_ids):
            textbook = await asyncio.to_thread(_load_textbook, file_id)
            if not textbook:
                logger.warning("跳过未解析的文件: %s", file_id)
                continue

            # 以路由层的 file_id 为准，保证向量元数据与文件列表一致
            # （历史解析结果里 textbook_id 可能残留存储文件名）
            textbook = textbook.model_copy(update={"textbook_id": file_id})

            chunks = await asyncio.to_thread(chunker.chunk_textbook, textbook)
            # 重新索引同一本教材时先移除旧片段，避免残留过期内容
            vector_store.remove_by_textbook(file_id)
            all_chunks.extend(chunks)
            indexed_ids.append(file_id)

            state_store.update(task_id, {
                "progress": round((position + 1) / len(file_ids) * 40, 1),
                "message": f"已切分《{textbook.title or textbook.filename}》",
            })

        if not all_chunks:
            raise ValueError("没有生成任何文本块，请先上传并解析教材")

        state_store.update(task_id, {"progress": 50.0, "message": "生成向量"})
        texts = [chunk.content for chunk in all_chunks]
        embeddings = await asyncio.to_thread(embedding_service.encode, texts)
        await asyncio.to_thread(embedding_service.flush)

        state_store.update(task_id, {"progress": 80.0, "message": "写入向量库"})
        vector_store.set_embedding_signature(embedding_service.signature)
        added = await asyncio.to_thread(
            vector_store.add_vectors, embeddings, [c.to_dict() for c in all_chunks]
        )
        await asyncio.to_thread(vector_store.save, "default")

        state_store.set(task_id, {
            "status": "completed",
            "progress": 100.0,
            "message": "索引建立完成",
            "error_message": None,
            "total_chunks": vector_store.size,
            "indexed_textbooks": len(indexed_ids),
            "indexed_textbook_ids": indexed_ids,
            "new_chunks": added,
        })
        logger.info("索引完成：新增 %d 个片段，共 %d 个", added, vector_store.size)

    except Exception as exc:  # noqa: BLE001
        logger.exception("建立索引失败")
        state_store.update(task_id, {
            "status": "failed",
            "progress": 0.0,
            "message": "索引建立失败",
            "error_message": str(exc),
        })


@router.post("/index", response_model=IndexResponse)
async def create_index(request: IndexRequest, background_tasks: BackgroundTasks):
    """建立向量索引。"""
    file_ids = list(dict.fromkeys(request.file_ids))

    available = [
        file_id for file_id in file_ids
        if (settings.textbooks_dir / f"{file_id}_parsed.json").exists()
    ]
    if not available:
        raise HTTPException(status_code=404, detail="所选文件尚未解析完成，无法建立索引")

    task_id = f"index_{uuid.uuid4().hex[:8]}"
    state_store.set(task_id, {
        "status": "pending",
        "progress": 0.0,
        "message": "任务已创建",
        "error_message": None,
        "total_chunks": 0,
    })
    background_tasks.add_task(_index_files, task_id, available)

    return IndexResponse(task_id=task_id, message=f"已开始为 {len(available)} 份教材建立索引")


@router.get("/index/status/{task_id}", response_model=IndexTaskStatus)
async def get_index_task_status(task_id: str):
    """查询索引任务进度。"""
    task = state_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="索引任务不存在")
    return IndexTaskStatus(
        task_id=task_id,
        status=task.get("status", "unknown"),
        progress=float(task.get("progress", 0.0) or 0.0),
        message=task.get("message"),
        error_message=task.get("error_message"),
        total_chunks=int(task.get("total_chunks", 0) or 0),
    )


@router.post("/query", response_model=QueryResponse)
async def query_knowledge(request: QueryRequest):
    """基于教材内容回答问题。"""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    vector_store = get_vector_store()
    if vector_store.size == 0:
        raise HTTPException(status_code=400, detail="知识库为空，请先建立索引")

    qa = get_qa_instance(top_k=settings.TOP_K)
    response = await qa.answer_question(question)

    return QueryResponse(
        answer=response.answer,
        citations=[c.to_dict() for c in response.citations],
        source_chunks=response.source_chunks,
        retrieved_count=response.retrieved_count,
        top_score=response.top_score,
    )


@router.get("/status", response_model=IndexStatus)
async def get_index_status():
    """获取索引状态。"""
    vector_store = get_vector_store()
    embedding_service = get_embedding_service()
    return IndexStatus(
        total_chunks=vector_store.size,
        indexed_textbooks=len(vector_store.indexed_textbook_ids()),
        is_ready=vector_store.size > 0,
        textbook_ids=vector_store.indexed_textbook_ids(),
        embedding_backend=embedding_service.backend,
        dimension=vector_store.dimension or 0,
    )


@router.delete("/index")
async def clear_index():
    """清空索引（含磁盘文件）。"""
    vector_store = get_vector_store()
    await asyncio.to_thread(vector_store.clear, True, "default")
    return {"message": "索引已清空"}


@router.get("/no-answer-text")
async def get_no_answer_text():
    """返回统一的"未找到"文案，便于前端对齐。"""
    return {"text": NO_ANSWER_TEXT}

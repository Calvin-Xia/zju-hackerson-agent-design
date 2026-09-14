"""知识图谱 API。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.routes.parse import normalize_textbook
from src.kg.extractor import extract_from_textbook
from src.kg.graph_store import graph_store
from src.kg.models import ExtractionStatus, ExtractionTaskStatus
from src.models.textbook import Textbook
from src.shared.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

_extraction_status: Dict[str, ExtractionTaskStatus] = {}


def rebuild_extraction_status_from_files() -> None:
    """启动时从磁盘重建提取状态。

    已完成的图谱标记为 completed；已解析但还没抽取出图谱的教材不写入状态，
    状态接口会返回 ``pending``，前端因此能显示「开始抽取」而不是一直轮询 404。
    """
    completed = 0
    for file_id in graph_store.list_graphs():
        graph = graph_store.load_safe(file_id)
        if graph and graph.nodes:
            _extraction_status[file_id] = ExtractionTaskStatus(
                file_id=file_id,
                status=ExtractionStatus.COMPLETED,
                progress=100.0,
                completed_at=graph.extracted_at or datetime.now(),
            )
            completed += 1

    if completed:
        logger.info("从磁盘重建了 %d 个知识图谱的提取状态", completed)


class ExtractRequest(BaseModel):
    file_id: str
    force: bool = False


class ExtractResponse(BaseModel):
    file_id: str
    message: str
    status: str


class NodeUpdateRequest(BaseModel):
    name: Optional[str] = None
    definition: Optional[str] = None
    category: Optional[str] = None


class RelationUpdateRequest(BaseModel):
    description: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


def _load_textbook(file_id: str) -> Optional[Textbook]:
    """读取已解析的教材数据（同步，供子线程调用）。"""
    parsed_path = settings.textbooks_dir / f"{file_id}_parsed.json"
    if not parsed_path.exists():
        return None
    try:
        with open(parsed_path, "r", encoding="utf-8") as f:
            textbook = Textbook.model_validate(json.load(f))
        return normalize_textbook(textbook, file_id)
    except Exception as exc:
        logger.error("加载教材失败 %s: %s", file_id, exc)
        return None


def _load_graph(file_id: str) -> Optional[KnowledgeGraph]:
    """读取知识图谱；文件损坏时返回 409 而不是静默当成"不存在"。"""
    try:
        return graph_store.load(file_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail="知识图谱文件已损坏，请重新提取",
        ) from exc


async def _extract_async(file_id: str) -> None:
    """异步执行知识点抽取。"""
    try:
        _extraction_status[file_id] = ExtractionTaskStatus(
            file_id=file_id,
            status=ExtractionStatus.EXTRACTING,
            progress=0.0,
            started_at=datetime.now(),
        )

        textbook = await asyncio.to_thread(_load_textbook, file_id)
        if not textbook:
            raise ValueError("未找到解析结果，请先完成教材解析")

        def progress_cb(progress: float, chapter_title: str = "") -> None:
            status = _extraction_status.get(file_id)
            if status:
                # 章节抽取占 0~95%，剩余进度留给图谱落盘
                status.progress = round(min(progress, 100.0) * 0.95, 1)
                if chapter_title:
                    status.current_chapter = chapter_title

        graph = await extract_from_textbook(textbook, progress_cb=progress_cb)
        await asyncio.to_thread(graph_store.save, file_id, graph)

        _extraction_status[file_id] = ExtractionTaskStatus(
            file_id=file_id,
            status=ExtractionStatus.COMPLETED,
            progress=100.0,
            completed_at=datetime.now(),
        )
        logger.info("知识图谱抽取完成: %s（%d 个知识点）", file_id, graph.total_nodes)

    except Exception as exc:  # noqa: BLE001
        logger.exception("知识图谱抽取失败: %s", file_id)
        _extraction_status[file_id] = ExtractionTaskStatus(
            file_id=file_id,
            status=ExtractionStatus.FAILED,
            progress=0.0,
            error_message=str(exc),
        )


@router.post("/extract", response_model=ExtractResponse)
async def extract_knowledge(request: ExtractRequest):
    """触发知识点提取。"""
    file_id = request.file_id

    textbook = await asyncio.to_thread(_load_textbook, file_id)
    if not textbook:
        raise HTTPException(status_code=404, detail="未找到已解析的教材，请先上传并等待解析完成")

    current = _extraction_status.get(file_id)
    if current and current.status == ExtractionStatus.EXTRACTING:
        return ExtractResponse(file_id=file_id, message="抽取正在进行中", status="extracting")

    existing = await asyncio.to_thread(_load_graph, file_id)
    if existing and existing.nodes and not request.force:
        return ExtractResponse(
            file_id=file_id,
            message="知识图谱已存在，如需重新抽取请使用 force=true",
            status="completed",
        )

    _extraction_status[file_id] = ExtractionTaskStatus(
        file_id=file_id,
        status=ExtractionStatus.PENDING,
        progress=0.0,
        started_at=datetime.now(),
    )

    task = asyncio.create_task(_extract_async(file_id))

    def _log_failure(completed_task: asyncio.Task) -> None:
        if completed_task.cancelled():
            return
        exc = completed_task.exception()
        if exc:
            logger.error("抽取任务异常: %s", exc)

    task.add_done_callback(_log_failure)

    return ExtractResponse(file_id=file_id, message="已开始抽取知识点", status="pending")


@router.get("/status/{file_id}")
async def get_extraction_status(file_id: str):
    """获取提取状态。"""
    status = _extraction_status.get(file_id)
    if status:
        return {
            "file_id": status.file_id,
            "status": status.status.value,
            "progress": status.progress,
            "current_chapter": status.current_chapter,
            "error_message": status.error_message,
        }

    graph = await asyncio.to_thread(_load_graph, file_id)
    if graph and graph.nodes:
        return {
            "file_id": file_id,
            "status": "completed",
            "progress": 100.0,
            "total_nodes": graph.total_nodes,
            "total_relations": graph.total_relations,
        }

    # 已解析但未抽取（含服务重启后的中间态）返回 pending 而不是 404，
    # 让前端停止轮询并展示「开始抽取」按钮
    textbook = await asyncio.to_thread(_load_textbook, file_id)
    if textbook:
        return {"file_id": file_id, "status": "pending", "progress": 0.0}

    raise HTTPException(status_code=404, detail="文件不存在或尚未解析")


@router.get("/graph/{file_id}")
async def get_knowledge_graph(
    file_id: str,
    page: int = 1,
    page_size: int = 100,
    category: Optional[str] = None,
    all: bool = False,
):
    """获取知识图谱数据（支持分页与分类筛选）。"""
    if page < 1:
        raise HTTPException(status_code=400, detail="page 必须 >= 1")
    if page_size < 1 or page_size > 1000:
        raise HTTPException(status_code=400, detail="page_size 必须在 1~1000 之间")

    graph = await asyncio.to_thread(_load_graph, file_id)
    if not graph:
        raise HTTPException(status_code=404, detail="知识图谱不存在")
    if not graph.nodes:
        raise HTTPException(status_code=409, detail="知识图谱为空，请重新抽取")

    nodes = graph.nodes
    if category:
        nodes = [n for n in nodes if n.category == category]

    total = len(nodes)
    if all:
        paginated_nodes = nodes
        page, page_size = 1, (total or 1)
    else:
        start = (page - 1) * page_size
        paginated_nodes = nodes[start:start + page_size]

    node_ids = {n.id for n in paginated_nodes}
    related_relations = [
        r for r in graph.relations if r.source in node_ids or r.target in node_ids
    ]

    return {
        "file_id": file_id,
        "textbook_title": graph.textbook_title,
        "nodes": [node.model_dump() for node in paginated_nodes],
        "links": [rel.model_dump() for rel in related_relations],
        "categories": sorted({n.category for n in graph.nodes if n.category}),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if page_size else 1,
        },
    }


@router.put("/graph/{file_id}/node/{node_id}")
async def update_node(file_id: str, node_id: str, request: NodeUpdateRequest):
    """更新知识点。"""
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    success = await asyncio.to_thread(graph_store.update_node, file_id, node_id, updates)
    if not success:
        raise HTTPException(status_code=404, detail="知识点不存在")
    return {"message": "知识点已更新"}


@router.put("/graph/{file_id}/relation")
async def update_relation(
    file_id: str,
    source: str,
    target: str,
    relation_type: str,
    request: RelationUpdateRequest,
):
    """更新关系。"""
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    success = await asyncio.to_thread(
        graph_store.update_relation, file_id, source, target, relation_type, updates
    )
    if not success:
        raise HTTPException(status_code=404, detail="关系不存在")
    return {"message": "关系已更新"}


@router.delete("/graph/{file_id}")
async def delete_knowledge_graph(file_id: str):
    """删除知识图谱。"""
    deleted = await asyncio.to_thread(graph_store.delete, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="知识图谱不存在")
    _extraction_status.pop(file_id, None)
    return {"message": "知识图谱已删除"}


@router.get("/graphs")
async def list_knowledge_graphs() -> List[Dict[str, object]]:
    """列出所有知识图谱。"""
    graphs: List[Dict[str, object]] = []
    for file_id in await asyncio.to_thread(graph_store.list_graphs):
        graph = await asyncio.to_thread(graph_store.load_safe, file_id)
        if not graph:
            continue
        graphs.append({
            "file_id": file_id,
            "textbook_id": graph.textbook_id,
            "textbook_title": graph.textbook_title,
            "total_nodes": graph.total_nodes,
            "total_relations": graph.total_relations,
            "extracted_at": graph.extracted_at.isoformat() if graph.extracted_at else None,
        })
    return graphs

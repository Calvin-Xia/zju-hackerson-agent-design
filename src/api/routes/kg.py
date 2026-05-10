import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.models.textbook import Textbook
from src.kg.models import ExtractionStatus, ExtractionTaskStatus, KnowledgeGraph
from src.kg.extractor import extract_from_textbook
from src.kg.graph_store import graph_store

logger = logging.getLogger(__name__)

router = APIRouter()

_extraction_status: Dict[str, ExtractionTaskStatus] = {}


class ExtractRequest(BaseModel):
    file_id: str


class ExtractResponse(BaseModel):
    file_id: str
    message: str


class KnowledgeGraphResponse(BaseModel):
    nodes: list
    links: list


def _load_textbook(file_id: str) -> Optional[Textbook]:
    """加载已解析的教材数据"""
    parsed_path = Path("data/textbooks") / f"{file_id}_parsed.json"

    if not parsed_path.exists():
        return None

    try:
        with open(parsed_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return Textbook.model_validate(data)
    except Exception as e:
        logger.error(f"Failed to load textbook: {e}")
        return None


async def _extract_async(file_id: str):
    """异步执行知识点提取"""
    try:
        _extraction_status[file_id] = ExtractionTaskStatus(
            file_id=file_id,
            status=ExtractionStatus.EXTRACTING,
            started_at=None,
        )

        textbook = _load_textbook(file_id)
        if not textbook:
            _extraction_status[file_id].status = ExtractionStatus.FAILED
            _extraction_status[file_id].error_message = "Textbook not found"
            return

        graph = await extract_from_textbook(textbook)

        graph_store.save(file_id, graph)

        _extraction_status[file_id].status = ExtractionStatus.COMPLETED
        _extraction_status[file_id].progress = 100.0

        logger.info(f"Knowledge extraction completed for {file_id}")

    except Exception as e:
        logger.error(f"Knowledge extraction failed for {file_id}: {e}")
        _extraction_status[file_id].status = ExtractionStatus.FAILED
        _extraction_status[file_id].error_message = str(e)


@router.post("/extract", response_model=ExtractResponse)
async def extract_knowledge(request: ExtractRequest):
    """触发知识点提取"""
    file_id = request.file_id

    textbook = _load_textbook(file_id)
    if not textbook:
        raise HTTPException(status_code=404, detail="Textbook not found")

    existing = graph_store.load(file_id)
    if existing:
        return ExtractResponse(
            file_id=file_id,
            message="Knowledge graph already exists",
        )

    _extraction_status[file_id] = ExtractionTaskStatus(
        file_id=file_id,
        status=ExtractionStatus.PENDING,
    )

    asyncio.create_task(_extract_async(file_id))

    return ExtractResponse(
        file_id=file_id,
        message="Knowledge extraction started",
    )


@router.get("/status/{file_id}")
async def get_extraction_status(file_id: str):
    """获取提取状态"""
    if file_id in _extraction_status:
        status = _extraction_status[file_id]
        return {
            "file_id": status.file_id,
            "status": status.status.value,
            "progress": status.progress,
            "error_message": status.error_message,
        }

    graph = graph_store.load(file_id)
    if graph:
        return {
            "file_id": file_id,
            "status": "completed",
            "progress": 100.0,
            "total_nodes": graph.total_nodes,
            "total_relations": graph.total_relations,
        }

    raise HTTPException(status_code=404, detail="Extraction status not found")


@router.get("/graph/{file_id}")
async def get_knowledge_graph(file_id: str):
    """获取知识图谱数据"""
    graph = graph_store.load(file_id)

    if not graph:
        raise HTTPException(status_code=404, detail="Knowledge graph not found")

    nodes = []
    for node in graph.nodes:
        nodes.append({
            "id": node.id,
            "name": node.name,
            "definition": node.definition,
            "category": node.category,
            "chapter": node.chapter,
            "frequency": node.frequency,
        })

    links = []
    for rel in graph.relations:
        links.append({
            "source": rel.source,
            "target": rel.target,
            "relation_type": rel.relation_type,
            "description": rel.description,
        })

    return {"nodes": nodes, "links": links}


@router.get("/graphs")
async def list_knowledge_graphs():
    """列出所有知识图谱"""
    file_ids = graph_store.list_graphs()

    graphs = []
    for file_id in file_ids:
        graph = graph_store.load(file_id)
        if graph:
            graphs.append({
                "file_id": file_id,
                "textbook_id": graph.textbook_id,
                "textbook_title": graph.textbook_title,
                "total_nodes": graph.total_nodes,
                "total_relations": graph.total_relations,
                "extracted_at": graph.extracted_at.isoformat() if graph.extracted_at else None,
            })

    return graphs

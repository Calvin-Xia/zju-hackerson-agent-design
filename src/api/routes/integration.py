"""跨教材整合 API。

整合逻辑位于 :mod:`src.integration.pipeline`，本模块只负责
任务调度、状态上报与结果查询。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from src.integration.pipeline import run_integration
from src.kg.graph_store import graph_store
from src.kg.models import KnowledgeGraph
from src.shared.config import settings
from src.shared.state_store import get_integration_store

logger = logging.getLogger(__name__)

router = APIRouter()

state_store = get_integration_store()


class MergeRequest(BaseModel):
    textbook_ids: List[str] = Field(..., min_length=1)


class MergeResponse(BaseModel):
    task_id: str
    message: str


class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
    message: Optional[str] = None
    error_message: Optional[str] = None


class DecisionResponse(BaseModel):
    decision_id: str
    action: str
    affected_nodes: List[str]
    result_node: Optional[str]
    reason: str
    confidence: float


class StatisticsResponse(BaseModel):
    original_textbook_count: int
    total_original_chars: int
    total_compressed_chars: int
    compression_ratio: float
    is_within_limit: bool
    max_compression_ratio: float
    total_decisions: int
    merge_count: int
    keep_count: int
    remove_count: int
    original_node_count: int
    compressed_node_count: int
    original_relation_count: int
    compressed_relation_count: int
    condensed_node_count: int = 0
    dropped_node_count: int = 0
    alignment_candidates: int = 0
    aligned_pair_count: int = 0


def _load_graphs(textbook_ids: List[str]) -> Dict[str, KnowledgeGraph]:
    """同步加载知识图谱（在子线程中调用，避免阻塞事件循环）。"""
    graphs: Dict[str, KnowledgeGraph] = {}
    for file_id in textbook_ids:
        graph = graph_store.load_safe(file_id)
        if graph and graph.nodes:
            graphs[file_id] = graph
    return graphs


async def _run_integration(task_id: str, textbook_ids: List[str]) -> None:
    """异步执行整合任务。"""
    try:
        state_store.update(task_id, {"status": "processing", "progress": 0.0, "message": "加载知识图谱"})

        graphs = await asyncio.to_thread(_load_graphs, textbook_ids)
        if not graphs:
            raise ValueError("未找到可用的知识图谱，请先完成知识点抽取")

        missing = [fid for fid in textbook_ids if fid not in graphs]
        if missing:
            logger.warning("以下教材没有可用图谱，已跳过: %s", missing)

        def progress_cb(progress: float, message: str) -> None:
            state_store.update(task_id, {"progress": round(progress, 1), "message": message})

        outcome = await run_integration(graphs, progress_cb=progress_cb)

        state_store.set(task_id, {
            "status": "completed",
            "progress": 100.0,
            "message": "整合完成",
            "error_message": None,
            "task_id": task_id,
            "textbook_ids": list(graphs.keys()),
            "requested_textbook_ids": textbook_ids,
            "skipped_textbook_ids": missing,
            "decisions": [d.to_dict() for d in outcome.decisions],
            "statistics": outcome.statistics(),
            "compressed_nodes": [n.model_dump() for n in outcome.nodes],
            "compressed_relations": [r.model_dump() for r in outcome.relations],
            "alignment": {
                "candidates": outcome.alignment.total_candidates,
                "pairs": len(outcome.alignment.aligned_pairs),
                "verified_by_llm": outcome.alignment.verified_by_llm,
                "pairs_detail": [
                    {
                        "node1_id": p.node1_id,
                        "node2_id": p.node2_id,
                        "node1_name": p.node1_name,
                        "node2_name": p.node2_name,
                        "similarity": round(p.similarity_score, 4),
                        "confidence": round(p.confidence, 4),
                        "reason": p.reason,
                    }
                    for p in outcome.alignment.aligned_pairs
                ],
            },
        })
        logger.info(
            "整合任务 %s 完成：压缩比 %.2f%%，决策 %d 条",
            task_id, outcome.stats.compression_ratio * 100, len(outcome.decisions),
        )

    except Exception as exc:  # noqa: BLE001 - 需要把失败原因回传给前端
        logger.exception("整合任务 %s 失败", task_id)
        state_store.set(task_id, {
            "status": "failed",
            "progress": 0.0,
            "message": "整合失败",
            "error_message": str(exc),
            "task_id": task_id,
            "textbook_ids": textbook_ids,
        })


@router.post("/merge", response_model=MergeResponse)
async def start_merge(request: MergeRequest, background_tasks: BackgroundTasks):
    """启动整合任务。"""
    if len(request.textbook_ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要选择 2 本教材才能进行整合")

    duplicate_free = list(dict.fromkeys(request.textbook_ids))

    graphs = await asyncio.to_thread(_load_graphs, duplicate_free)
    if not graphs:
        raise HTTPException(
            status_code=404,
            detail="所选教材都没有可用的知识图谱，请先完成知识点抽取",
        )

    task_id = f"integration_{uuid.uuid4().hex[:8]}"
    state_store.set(task_id, {
        "status": "pending",
        "progress": 0.0,
        "message": "任务已创建",
        "error_message": None,
        "textbook_ids": duplicate_free,
    })

    background_tasks.add_task(_run_integration, task_id, duplicate_free)

    return MergeResponse(
        task_id=task_id,
        message=f"已开始整合 {len(graphs)} 本教材",
    )


@router.get("/status/{task_id}", response_model=TaskStatus)
async def get_integration_status(task_id: str):
    """获取整合状态。"""
    task = state_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="整合任务不存在")
    return TaskStatus(
        task_id=task_id,
        status=task.get("status", "unknown"),
        progress=float(task.get("progress", 0.0) or 0.0),
        message=task.get("message"),
        error_message=task.get("error_message"),
    )


@router.get("/decisions/{task_id}", response_model=List[DecisionResponse])
async def get_integration_decisions(task_id: str):
    """获取整合决策。"""
    result = state_store.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="整合结果不存在")
    if result.get("status") == "failed":
        raise HTTPException(
            status_code=409,
            detail=result.get("error_message") or "整合任务失败",
        )

    return [
        DecisionResponse(
            decision_id=d["decision_id"],
            action=d["action"],
            affected_nodes=d["affected_nodes"],
            result_node=d.get("result_node"),
            reason=d["reason"],
            confidence=d["confidence"],
        )
        for d in result.get("decisions", [])
    ]


@router.get("/statistics/{task_id}", response_model=StatisticsResponse)
async def get_integration_statistics(task_id: str):
    """获取整合统计。"""
    result = state_store.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="整合结果不存在")
    if result.get("status") == "failed":
        raise HTTPException(status_code=409, detail=result.get("error_message") or "整合任务失败")
    if result.get("status") != "completed":
        raise HTTPException(status_code=409, detail="整合任务尚未完成")

    stats = dict(result.get("statistics", {}))
    stats.setdefault("max_compression_ratio", settings.MAX_COMPRESSION_RATIO)
    return StatisticsResponse(**stats)


@router.get("/alignment/{task_id}")
async def get_integration_alignment(task_id: str):
    """获取语义对齐明细。"""
    result = state_store.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="整合结果不存在")
    return result.get("alignment", {"candidates": 0, "pairs": 0, "pairs_detail": []})


@router.get("/graph/{task_id}")
async def get_integrated_graph(task_id: str):
    """获取整合后的知识图谱。"""
    result = state_store.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="整合结果不存在")
    if result.get("status") == "failed":
        raise HTTPException(status_code=409, detail=result.get("error_message") or "整合任务失败")

    return {
        "nodes": result.get("compressed_nodes", []),
        "links": result.get("compressed_relations", []),
        "statistics": result.get("statistics", {}),
    }


@router.get("/tasks")
async def list_integration_tasks(limit: int = 20):
    """列出最近的整合任务（按文件修改时间倒序）。"""
    limit = max(1, min(limit, 200))
    tasks: List[Dict[str, Any]] = []
    paths = sorted(
        Path(state_store.storage_path).glob("integration_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]

    for path in paths:
        data = state_store.get(path.stem)
        if not data:
            continue
        tasks.append({
            "task_id": path.stem,
            "status": data.get("status"),
            "progress": data.get("progress", 0.0),
            "textbook_ids": data.get("textbook_ids", []),
            "statistics": data.get("statistics", {}),
        })
    return tasks

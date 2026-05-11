"""
整合API端点模块

提供跨教材知识整合的REST API：
- POST /merge - 启动整合任务
- GET /status/{task_id} - 查询整合状态
- GET /decisions - 查询整合决策
- GET /statistics - 查询整合统计
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Any
from pathlib import Path
import json

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from src.integration.alignment import SemanticAligner, AlignmentResult
from src.integration.decision import DecisionMaker, DecisionResult, IntegrationDecision
from src.integration.compression import CompressionController, CompressionStats
from src.kg.graph_store import graph_store
from src.kg.models import KnowledgeGraph

logger = logging.getLogger(__name__)

router = APIRouter()


class MergeRequest(BaseModel):
    textbook_ids: List[str]


class MergeResponse(BaseModel):
    task_id: str
    message: str


class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: float
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
    total_decisions: int
    merge_count: int
    keep_count: int
    remove_count: int
    original_node_count: int
    compressed_node_count: int
    original_relation_count: int
    compressed_relation_count: int


integration_tasks: Dict[str, Dict[str, Any]] = {}
integration_results: Dict[str, Dict[str, Any]] = {}


def _save_integration_result(task_id: str, result: Dict[str, Any]):
    """保存整合结果到文件"""
    result_dir = Path("data/integration")
    result_dir.mkdir(parents=True, exist_ok=True)
    
    result_file = result_dir / f"{task_id}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    integration_results[task_id] = result


def _load_integration_result(task_id: str) -> Optional[Dict[str, Any]]:
    """从文件加载整合结果"""
    if task_id in integration_results:
        return integration_results[task_id]
    
    result_file = Path("data/integration") / f"{task_id}.json"
    if result_file.exists():
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                result = json.load(f)
            integration_results[task_id] = result
            return result
        except Exception as e:
            logger.error(f"Failed to load integration result: {e}")
    
    return None


async def _run_integration(task_id: str, textbook_ids: List[str]):
    """异步执行整合任务"""
    try:
        integration_tasks[task_id] = {
            "status": "processing",
            "progress": 0.0,
            "error_message": None
        }
        
        graphs: Dict[str, KnowledgeGraph] = {}
        for file_id in textbook_ids:
            graph = graph_store.load(file_id)
            if graph:
                graphs[file_id] = graph
        
        if not graphs:
            raise ValueError("No valid knowledge graphs found")
        
        integration_tasks[task_id]["progress"] = 10.0
        
        all_nodes = []
        nodes_map = {}
        for file_id, graph in graphs.items():
            for node in graph.nodes:
                all_nodes.append(node)
                nodes_map[node.id] = node
        
        textbook_nodes = {
            file_id: list(graph.nodes)
            for file_id, graph in graphs.items()
        }
        
        aligner = SemanticAligner(similarity_threshold=0.7, use_llm_verification=False)
        alignment_results = await aligner.align_multiple_textbooks(textbook_nodes)
        
        integration_tasks[task_id]["progress"] = 40.0
        
        all_aligned_pairs = []
        for result in alignment_results:
            all_aligned_pairs.extend(result.aligned_pairs)
        
        decision_maker = DecisionMaker()
        decision_result = await decision_maker.make_decisions_for_aligned_pairs(
            all_aligned_pairs, nodes_map
        )
        
        integration_tasks[task_id]["progress"] = 70.0
        
        controller = CompressionController()
        original_nodes = all_nodes
        original_relations = []
        for graph in graphs.values():
            original_relations.extend(graph.relations)
        
        compressed_nodes = list(all_nodes)
        compressed_relations = list(original_relations)
        
        for decision in decision_result.decisions:
            if decision.action.value == "remove":
                compressed_nodes = [
                    n for n in compressed_nodes
                    if n.id not in decision.affected_nodes
                ]
            elif decision.action.value == "merge":
                if decision.result_node and decision.affected_nodes:
                    keep_id = decision.result_node
                    remove_ids = [nid for nid in decision.affected_nodes if nid != keep_id]
                    compressed_nodes = [
                        n for n in compressed_nodes
                        if n.id not in remove_ids
                    ]
        
        compressed_node_ids = {n.id for n in compressed_nodes}
        compressed_relations = [
            r for r in compressed_relations
            if r.source in compressed_node_ids and r.target in compressed_node_ids
        ]
        
        compression_stats = controller.compute_compression_stats(
            original_nodes, original_relations,
            compressed_nodes, compressed_relations
        )
        
        integration_tasks[task_id]["progress"] = 90.0
        
        result = {
            "task_id": task_id,
            "textbook_ids": textbook_ids,
            "decisions": [d.to_dict() for d in decision_result.decisions],
            "statistics": {
                "original_textbook_count": len(textbook_ids),
                "total_original_chars": compression_stats.original_total_chars,
                "total_compressed_chars": compression_stats.compressed_total_chars,
                "compression_ratio": compression_stats.compression_ratio,
                "total_decisions": decision_result.total_decisions,
                "merge_count": decision_result.merge_count,
                "keep_count": decision_result.keep_count,
                "remove_count": decision_result.remove_count,
                "original_node_count": compression_stats.original_node_count,
                "compressed_node_count": compression_stats.compressed_node_count,
                "original_relation_count": compression_stats.original_relation_count,
                "compressed_relation_count": compression_stats.compressed_relation_count
            },
            "compressed_nodes": [n.model_dump() for n in compressed_nodes],
            "compressed_relations": [r.model_dump() for r in compressed_relations]
        }
        
        _save_integration_result(task_id, result)
        
        integration_tasks[task_id] = {
            "status": "completed",
            "progress": 100.0,
            "error_message": None
        }
        
        logger.info(f"Integration task {task_id} completed")
        
    except Exception as e:
        logger.error(f"Integration task {task_id} failed: {e}")
        integration_tasks[task_id] = {
            "status": "failed",
            "progress": 0.0,
            "error_message": str(e)
        }


@router.post("/merge", response_model=MergeResponse)
async def start_merge(request: MergeRequest, background_tasks: BackgroundTasks):
    """启动整合任务"""
    if not request.textbook_ids:
        raise HTTPException(status_code=400, detail="No textbook IDs provided")
    
    for file_id in request.textbook_ids:
        graph = graph_store.load(file_id)
        if not graph:
            raise HTTPException(status_code=404, detail=f"Knowledge graph not found: {file_id}")
    
    task_id = f"integration_{uuid.uuid4().hex[:8]}"
    
    background_tasks.add_task(_run_integration, task_id, request.textbook_ids)
    
    return MergeResponse(
        task_id=task_id,
        message=f"Integration started for {len(request.textbook_ids)} textbooks"
    )


@router.get("/status/{task_id}", response_model=TaskStatus)
async def get_integration_status(task_id: str):
    """获取整合状态"""
    if task_id in integration_tasks:
        task = integration_tasks[task_id]
        return TaskStatus(
            task_id=task_id,
            status=task["status"],
            progress=task["progress"],
            error_message=task.get("error_message")
        )
    
    result = _load_integration_result(task_id)
    if result:
        return TaskStatus(
            task_id=task_id,
            status="completed",
            progress=100.0
        )
    
    raise HTTPException(status_code=404, detail="Integration task not found")


@router.get("/decisions/{task_id}", response_model=List[DecisionResponse])
async def get_integration_decisions(task_id: str):
    """获取整合决策"""
    result = _load_integration_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Integration result not found")
    
    decisions = result.get("decisions", [])
    return [
        DecisionResponse(
            decision_id=d["decision_id"],
            action=d["action"],
            affected_nodes=d["affected_nodes"],
            result_node=d.get("result_node"),
            reason=d["reason"],
            confidence=d["confidence"]
        )
        for d in decisions
    ]


@router.get("/statistics/{task_id}", response_model=StatisticsResponse)
async def get_integration_statistics(task_id: str):
    """获取整合统计"""
    result = _load_integration_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Integration result not found")
    
    stats = result.get("statistics", {})
    return StatisticsResponse(**stats)


@router.get("/graph/{task_id}")
async def get_integrated_graph(task_id: str):
    """获取整合后的知识图谱"""
    result = _load_integration_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Integration result not found")
    
    return {
        "nodes": result.get("compressed_nodes", []),
        "links": result.get("compressed_relations", [])
    }

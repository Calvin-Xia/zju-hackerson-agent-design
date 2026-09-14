"""教材文件列表 API。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.routes.parse import get_parse_status, raw_file_for
from src.shared.config import settings
from src.shared.utils import resolve_display_title
from src.vectorstore.faiss_store import get_vector_store

logger = logging.getLogger(__name__)

router = APIRouter()


class FileInfo(BaseModel):
    file_id: str
    filename: str
    size: int
    status: str
    parse_status: str = "pending"
    chapter_count: int = 0
    total_chars: int = 0
    error_message: Optional[str] = None
    has_graph: bool = False
    textbook_title: str = ""


def _collect_files() -> List[FileInfo]:
    """扫描教材目录（同步，供子线程调用）。"""
    data_dir = settings.textbooks_dir
    if not data_dir.exists():
        return []

    files: List[FileInfo] = []
    parsed_ids = {
        path.name[: -len("_parsed.json")]
        for path in data_dir.glob("*_parsed.json")
    }

    for file_path in sorted(data_dir.iterdir()):
        if not file_path.is_file() or file_path.name.endswith("_parsed.json"):
            continue
        if file_path.name.startswith("."):
            continue

        file_id, _, filename = file_path.name.partition("_")
        if not filename:
            file_id, filename = file_path.stem, file_path.name

        record = get_parse_status(file_id)
        chapter_count = 0
        total_chars = 0
        error_message: Optional[str] = None
        textbook_title = ""

        if record:
            parse_status = record["status"]
            chapter_count = record.get("chapter_count", 0)
            total_chars = record.get("total_chars", 0)
            error_message = record.get("error_message")
            textbook_title = record.get("textbook_title", "")
        elif file_id in parsed_ids:
            parse_status = "completed"
            parsed_path = data_dir / f"{file_id}_parsed.json"
            try:
                with open(parsed_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                chapter_count = len(data.get("chapters", []))
                total_chars = data.get("total_chars", 0)
                textbook_title = resolve_display_title(
                    data.get("title", ""), data.get("filename", ""), file_id
                )
            except Exception as exc:
                logger.warning("读取解析结果失败 %s: %s", parsed_path.name, exc)
        else:
            # 有原始文件却没有解析结果：解析被中断（例如服务重启）。
            # 返回 failed 而不是 pending，避免前端无限轮询。
            parse_status = "failed"
            error_message = "解析未完成（可能因服务重启中断），可点击重新解析"

        files.append(
            FileInfo(
                file_id=file_id,
                filename=filename,
                size=file_path.stat().st_size,
                status="done",
                parse_status=parse_status,
                chapter_count=chapter_count,
                total_chars=total_chars,
                error_message=error_message,
                has_graph=(settings.knowledge_graphs_dir / f"{file_id}_kg.json").exists(),
                textbook_title=textbook_title,
            )
        )

    return files


@router.get("/", response_model=List[FileInfo])
async def list_files() -> List[FileInfo]:
    """列出所有已上传的教材。"""
    return await asyncio.to_thread(_collect_files)


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """删除教材及其派生数据（解析结果、知识图谱、向量索引）。"""
    data_dir = settings.textbooks_dir
    raw = raw_file_for(file_id)
    parsed = data_dir / f"{file_id}_parsed.json"
    if not raw and not parsed.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        for path in (raw, parsed, settings.knowledge_graphs_dir / f"{file_id}_kg.json"):
            if path and path.exists():
                path.unlink()
    except OSError as exc:
        logger.error("删除文件失败 %s: %s", file_id, exc)
        raise HTTPException(status_code=500, detail="删除文件失败") from exc

    # 同步移除向量索引中的片段，否则该教材内容仍会被 RAG 检索到
    vector_store = get_vector_store()
    if vector_store.remove_by_textbook(file_id) > 0:
        try:
            await asyncio.to_thread(vector_store.save, "default")
        except Exception as exc:  # 索引落盘失败不应阻塞删除
            logger.warning("保存向量索引失败: %s", exc)

    from src.api.routes.kg import _extraction_status
    from src.api.routes.parse import _parse_status

    _parse_status.pop(file_id, None)
    _extraction_status.pop(file_id, None)

    return {"message": "文件及派生数据已删除"}

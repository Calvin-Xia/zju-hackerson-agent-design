"""教材解析与解析状态 API。"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.models.parse_status import ParseStatus
from src.models.textbook import Textbook
from src.parsers.factory import parse_file
from src.shared.config import settings
from src.shared.utils import resolve_display_title

logger = logging.getLogger(__name__)

router = APIRouter()

# 内存中的解析状态存储
_parse_status: Dict[str, dict] = {}


def normalize_textbook(textbook: Textbook, file_id: str) -> Textbook:
    """统一由 file_id 决定教材身份，并修正历史数据里带 UUID 前缀的标题。

    旧版本解析时把 ``{file_id}_{原名}`` 整个当成教材 ID 与标题，
    这里在不重新解析的前提下做一次就地纠正；若标题看起来是解析器从
    正文里提取出来的（与存储名不同），则保持不变。
    """
    updates: Dict[str, str] = {}
    if textbook.textbook_id != file_id:
        updates["textbook_id"] = file_id

    nice_title = resolve_display_title(textbook.title, textbook.filename, file_id)
    if nice_title != textbook.title:
        updates["title"] = nice_title

    return textbook.model_copy(update=updates) if updates else textbook


def raw_file_for(file_id: str) -> Optional[Path]:
    """按 file_id 找到原始上传文件。"""
    data_dir = settings.textbooks_dir
    if not data_dir.exists():
        return None
    for path in data_dir.iterdir():
        if (
            path.is_file()
            and path.name.startswith(f"{file_id}_")
            and not path.name.endswith("_parsed.json")
        ):
            return path
    return None


def parsed_path_for(file_id: str) -> Path:
    return settings.textbooks_dir / f"{file_id}_parsed.json"


def update_parse_status(
    file_id: str,
    status: ParseStatus,
    error_message: Optional[str] = None,
    chapter_count: int = 0,
    total_chars: int = 0,
    textbook_title: str = "",
) -> None:
    """更新解析状态。"""
    _parse_status[file_id] = {
        "status": status.value,
        "error_message": error_message,
        "chapter_count": chapter_count,
        "total_chars": total_chars,
        "textbook_title": textbook_title,
    }


def get_parse_status(file_id: str) -> Optional[dict]:
    """获取解析状态。"""
    return _parse_status.get(file_id)


def rebuild_parse_status_from_files() -> None:
    """启动时从文件系统重建解析状态。

    有 ``_parsed.json`` 的标记为 completed；只有原始文件、没有解析结果的
    标记为 failed（解析被中断），避免前端无限轮询 pending。
    """
    data_dir = settings.textbooks_dir
    if not data_dir.exists():
        return

    completed = 0
    interrupted = 0

    for parsed_file in data_dir.glob("*_parsed.json"):
        file_id = parsed_file.name[: -len("_parsed.json")]
        try:
            with open(parsed_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            update_parse_status(
                file_id,
                ParseStatus.COMPLETED,
                chapter_count=len(data.get("chapters", [])),
                total_chars=data.get("total_chars", 0),
                textbook_title=resolve_display_title(
                    data.get("title", ""), data.get("filename", ""), file_id
                ),
            )
            completed += 1
        except Exception as exc:
            logger.warning("从 %s 重建解析状态失败: %s", parsed_file.name, exc)
            update_parse_status(
                file_id, ParseStatus.FAILED, error_message=f"解析结果损坏: {exc}"
            )

    for raw_path in data_dir.iterdir():
        if not raw_path.is_file() or raw_path.name.endswith("_parsed.json"):
            continue
        file_id = raw_path.name.partition("_")[0]
        if file_id not in _parse_status:
            update_parse_status(
                file_id,
                ParseStatus.FAILED,
                error_message="解析未完成（可能因服务重启中断），可点击重新解析",
            )
            interrupted += 1

    if completed or interrupted:
        logger.info("重建解析状态：完成 %d 个，中断 %d 个", completed, interrupted)


class ParseStatusResponse(BaseModel):
    file_id: str
    status: str
    error_message: Optional[str] = None
    chapter_count: int = 0
    total_chars: int = 0
    textbook_title: str = ""


async def parse_file_by_id(file_id: str) -> None:
    """解析（或重新解析）指定文件的教材内容。"""
    raw_path = raw_file_for(file_id)
    if not raw_path:
        update_parse_status(file_id, ParseStatus.FAILED, error_message="原始文件不存在")
        return

    try:
        update_parse_status(file_id, ParseStatus.PARSING)

        textbook = await parse_file(raw_path)

        result_path = parsed_path_for(file_id)
        await asyncio.to_thread(
            result_path.write_text, textbook.model_dump_json(indent=2), "utf-8"
        )

        update_parse_status(
            file_id,
            ParseStatus.COMPLETED,
            chapter_count=len(textbook.chapters),
            total_chars=textbook.total_chars,
            textbook_title=textbook.title,
        )
        logger.info("解析完成: %s（%d 章）", file_id, len(textbook.chapters))

    except Exception as exc:  # noqa: BLE001
        logger.exception("解析失败: %s", file_id)
        update_parse_status(file_id, ParseStatus.FAILED, error_message=str(exc))


@router.post("/{file_id}/parse")
async def start_parse(file_id: str):
    """对已上传的文件（重新）触发解析。"""
    raw_path = raw_file_for(file_id)
    if not raw_path:
        raise HTTPException(status_code=404, detail="原始文件不存在")

    current = get_parse_status(file_id)
    if current and current["status"] == ParseStatus.PARSING.value:
        return {"file_id": file_id, "status": "parsing", "message": "解析正在进行中"}

    update_parse_status(file_id, ParseStatus.PENDING)
    task = asyncio.create_task(parse_file_by_id(file_id))

    def _log_failure(completed_task: asyncio.Task) -> None:
        if completed_task.cancelled():
            return
        exc = completed_task.exception()
        if exc:
            logger.error("解析任务异常: %s", exc)

    task.add_done_callback(_log_failure)

    return {"file_id": file_id, "status": "pending", "message": "已开始解析"}


@router.get("/status/{file_id}", response_model=ParseStatusResponse)
async def get_parse_status_api(file_id: str) -> ParseStatusResponse:
    """获取文件解析状态。"""
    status = get_parse_status(file_id)

    result_path = parsed_path_for(file_id)
    if not status and result_path.exists():
        try:
            data = await asyncio.to_thread(
                lambda: json.loads(result_path.read_text(encoding="utf-8"))
            )
            update_parse_status(
                file_id,
                ParseStatus.COMPLETED,
                None,
                len(data.get("chapters", [])),
                data.get("total_chars", 0),
                resolve_display_title(
                    data.get("title", ""), data.get("filename", ""), file_id
                ),
            )
            status = get_parse_status(file_id)
        except Exception as exc:
            logger.error("读取解析结果失败: %s", exc)

    if not status:
        if raw_file_for(file_id):
            # 有原始文件但没有解析记录：解析被中断
            return ParseStatusResponse(
                file_id=file_id,
                status=ParseStatus.FAILED.value,
                error_message="解析未完成（可能因服务重启中断），可点击重新解析",
            )
        raise HTTPException(status_code=404, detail=f"未找到文件: {file_id}")

    return ParseStatusResponse(
        file_id=file_id,
        status=status["status"],
        error_message=status.get("error_message"),
        chapter_count=status.get("chapter_count", 0),
        total_chars=status.get("total_chars", 0),
        textbook_title=status.get("textbook_title", ""),
    )

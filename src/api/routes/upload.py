"""教材上传 API。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.routes.parse import parse_file_by_id, update_parse_status
from src.models.parse_status import ParseStatus
from src.shared.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

READ_CHUNK_SIZE = 1024 * 1024  # 1MB


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    size: int
    message: str


async def _save_upload(file: UploadFile, destination: Path, max_bytes: int) -> int:
    """流式写入上传文件，边写边校验大小，避免一次性读入内存。

    任何失败（含客户端中断）都会删除半成品文件，避免留下孤儿文件 ——
    这类文件会被文件列表当成"上传成功但解析失败"，误导用户。
    """
    total = 0
    try:
        with open(destination, "wb") as target:
            while True:
                chunk = await file.read(READ_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过大小上限 {settings.MAX_UPLOAD_SIZE_MB}MB",
                    )
                target.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except OSError as exc:
        destination.unlink(missing_ok=True)
        logger.error("保存上传文件失败: %s", exc)
        raise HTTPException(status_code=500, detail="保存文件失败") from exc
    except Exception as exc:  # 客户端中断等
        destination.unlink(missing_ok=True)
        logger.warning("上传中断，已清理临时文件 %s: %s", destination.name, exc)
        raise

    return total


@router.post("/", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
    """上传教材文件并自动开始解析。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    safe_filename = Path(file.filename).name
    extension = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
    allowed_extensions = settings.allowed_extensions
    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式：{extension or '未知'}，"
                   f"支持 {', '.join(allowed_extensions)}",
        )

    settings.textbooks_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    file_path = settings.textbooks_dir / f"{file_id}_{safe_filename}"

    size = await _save_upload(file, file_path, settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024)
    logger.info("文件已保存: %s（%d 字节）", file_path.name, size)

    update_parse_status(file_id, ParseStatus.PENDING)
    task = asyncio.create_task(parse_file_by_id(file_id))

    def _log_failure(completed_task: asyncio.Task) -> None:
        if completed_task.cancelled():
            return
        exc = completed_task.exception()
        if exc:
            logger.error("解析任务异常: %s", exc)

    task.add_done_callback(_log_failure)

    return UploadResponse(
        file_id=file_id,
        filename=safe_filename,
        size=size,
        message="上传成功，已开始解析",
    )

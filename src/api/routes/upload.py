import uuid
import asyncio
import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from src.shared.config import settings
from src.parsers.factory import parse_file
from src.api.routes.parse import update_parse_status
from src.models.parse_status import ParseStatus

logger = logging.getLogger(__name__)

router = APIRouter()


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    size: int
    message: str


@router.post("/", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    extension = file.filename.split(".")[-1].lower()
    if extension not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {extension}",
        )

    content = await file.read()
    file_size = len(content)
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    file_id = str(uuid.uuid4())
    file_path = Path("data/textbooks") / f"{file_id}_{file.filename}"

    try:
        with open(file_path, "wb") as f:
            f.write(content)
        logger.info(f"File saved: {file_path}")
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    # 异步触发解析
    update_parse_status(file_id, ParseStatus.PENDING)
    asyncio.create_task(_parse_file_async(file_id, file_path))

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        size=file_size,
        message="File uploaded successfully",
    )


async def _parse_file_async(file_id: str, file_path: Path):
    """异步解析文件"""
    try:
        update_parse_status(file_id, ParseStatus.PARSING)
        
        textbook = await parse_file(file_path)
        
        # 保存解析结果
        result_path = file_path.parent / f"{file_id}_parsed.json"
        with open(result_path, 'w', encoding='utf-8') as f:
            f.write(textbook.model_dump_json(indent=2))
        
        update_parse_status(
            file_id,
            ParseStatus.COMPLETED,
            chapter_count=len(textbook.chapters),
            total_chars=textbook.total_chars
        )
        logger.info(f"Parsing completed: {file_id}, chapters: {len(textbook.chapters)}")
    
    except Exception as e:
        logger.error(f"Parsing failed for {file_id}: {e}")
        update_parse_status(file_id, ParseStatus.FAILED, error_message=str(e))

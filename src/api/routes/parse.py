import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.models.parse_status import ParseStatus

logger = logging.getLogger(__name__)

router = APIRouter()

# 内存中的解析状态存储
_parse_status: dict[str, dict] = {}


class ParseStatusResponse(BaseModel):
    file_id: str
    status: str
    error_message: Optional[str] = None
    chapter_count: int = 0
    total_chars: int = 0


def update_parse_status(file_id: str, status: ParseStatus, error_message: Optional[str] = None, chapter_count: int = 0, total_chars: int = 0):
    """更新解析状态"""
    _parse_status[file_id] = {
        "status": status.value,
        "error_message": error_message,
        "chapter_count": chapter_count,
        "total_chars": total_chars
    }


def get_parse_status(file_id: str) -> Optional[dict]:
    """获取解析状态"""
    return _parse_status.get(file_id)


@router.get("/status/{file_id}", response_model=ParseStatusResponse)
async def get_parse_status_api(file_id: str):
    """获取文件解析状态"""
    # 先检查内存中的状态
    status = get_parse_status(file_id)
    
    if status:
        return ParseStatusResponse(
            file_id=file_id,
            status=status["status"],
            error_message=status["error_message"],
            chapter_count=status["chapter_count"],
            total_chars=status["total_chars"]
        )
    
    # 检查是否有解析结果文件
    result_path = Path("data/textbooks") / f"{file_id}_parsed.json"
    if result_path.exists():
        try:
            with open(result_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            chapter_count = len(data.get("chapters", []))
            total_chars = data.get("total_chars", 0)
            
            # 更新内存状态
            update_parse_status(file_id, ParseStatus.COMPLETED, chapter_count=chapter_count, total_chars=total_chars)
            
            return ParseStatusResponse(
                file_id=file_id,
                status=ParseStatus.COMPLETED.value,
                chapter_count=chapter_count,
                total_chars=total_chars
            )
        except Exception as e:
            logger.error(f"Failed to read parse result: {e}")
    
    # 文件不存在或未解析
    raise HTTPException(status_code=404, detail=f"Parse status not found for file: {file_id}")

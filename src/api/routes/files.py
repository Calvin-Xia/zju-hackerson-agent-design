import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.routes.parse import get_parse_status
from src.models.parse_status import ParseStatus

logger = logging.getLogger(__name__)

router = APIRouter()


class FileInfo(BaseModel):
    file_id: str
    filename: str
    size: int
    status: str
    parse_status: str = "pending"
    chapter_count: int = 0
    error_message: Optional[str] = None


@router.get("/", response_model=List[FileInfo])
async def list_files():
    data_dir = Path("data/textbooks")
    if not data_dir.exists():
        return []

    files = []
    for file_path in data_dir.iterdir():
        if file_path.is_file() and not file_path.name.endswith("_parsed.json"):
            parts = file_path.name.split("_", 1)
            if len(parts) == 2:
                file_id = parts[0]
                filename = parts[1]
            else:
                file_id = file_path.stem
                filename = file_path.name

            # 获取解析状态
            parse_status_data = get_parse_status(file_id)
            parse_status = "pending"
            chapter_count = 0
            error_message = None
            
            if parse_status_data:
                parse_status = parse_status_data["status"]
                chapter_count = parse_status_data["chapter_count"]
                error_message = parse_status_data["error_message"]
            elif (data_dir / f"{file_id}_parsed.json").exists():
                parse_status = "completed"

            files.append(
                FileInfo(
                    file_id=file_id,
                    filename=filename,
                    size=file_path.stat().st_size,
                    status="done",
                    parse_status=parse_status,
                    chapter_count=chapter_count,
                    error_message=error_message,
                )
            )

    return files

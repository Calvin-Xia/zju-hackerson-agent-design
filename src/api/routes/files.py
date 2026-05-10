import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class FileInfo(BaseModel):
    file_id: str
    filename: str
    size: int
    status: str


@router.get("/", response_model=List[FileInfo])
async def list_files():
    data_dir = Path("data/textbooks")
    if not data_dir.exists():
        return []

    files = []
    for file_path in data_dir.iterdir():
        if file_path.is_file():
            parts = file_path.name.split("_", 1)
            if len(parts) == 2:
                file_id = parts[0]
                filename = parts[1]
            else:
                file_id = file_path.stem
                filename = file_path.name

            files.append(
                FileInfo(
                    file_id=file_id,
                    filename=filename,
                    size=file_path.stat().st_size,
                    status="done",
                )
            )

    return files

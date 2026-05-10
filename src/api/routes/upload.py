import uuid
import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from src.shared.config import settings

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

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        size=file_size,
        message="File uploaded successfully",
    )

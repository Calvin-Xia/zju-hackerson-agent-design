from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ParseStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileInfo(BaseModel):
    file_id: str = Field(..., description="文件ID")
    filename: str = Field(..., description="文件名")
    format: str = Field("", description="文件格式")
    size: int = Field(0, description="文件大小(bytes)")
    status: ParseStatus = Field(ParseStatus.PENDING, description="解析状态")
    error_message: Optional[str] = Field(None, description="错误信息")
    chapter_count: int = Field(0, description="章节数量")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc), description="创建时间")

    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "abc123",
                "filename": "生理学.pdf",
                "format": "pdf",
                "size": 1024000,
                "status": "completed",
                "error_message": None,
                "chapter_count": 10,
                "created_at": "2024-01-01T00:00:00"
            }
        }

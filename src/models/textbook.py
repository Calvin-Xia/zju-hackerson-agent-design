from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Chapter(BaseModel):
    chapter_id: str = Field(..., description="章节ID，如 ch_01")
    title: str = Field(..., description="章节标题")
    page_start: int = Field(0, description="起始页码")
    page_end: int = Field(0, description="结束页码")
    content: str = Field("", description="章节正文内容")
    char_count: int = Field(0, description="字符数")

    class Config:
        json_schema_extra = {
            "example": {
                "chapter_id": "ch_01",
                "title": "第一章 绪论",
                "page_start": 1,
                "page_end": 15,
                "content": "生理学是研究生物体正常生命活动规律的科学...",
                "char_count": 8500
            }
        }


class Textbook(BaseModel):
    textbook_id: str = Field(..., description="教材ID")
    filename: str = Field(..., description="原始文件名")
    title: str = Field("", description="教材标题")
    total_pages: int = Field(0, description="总页数")
    total_chars: int = Field(0, description="总字符数")
    chapters: List[Chapter] = Field(default_factory=list, description="章节列表")
    parsed_at: Optional[datetime] = Field(None, description="解析时间")

    class Config:
        json_schema_extra = {
            "example": {
                "textbook_id": "book_01",
                "filename": "生理学.pdf",
                "title": "生理学",
                "total_pages": 520,
                "total_chars": 385000,
                "chapters": [],
                "parsed_at": "2024-01-01T00:00:00"
            }
        }

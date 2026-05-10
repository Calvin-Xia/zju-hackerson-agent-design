from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ExtractionStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    FAILED = "failed"


class KnowledgeNode(BaseModel):
    id: str = Field(..., description="节点ID")
    name: str = Field(..., description="知识点名称")
    definition: str = Field("", description="定义/解释")
    category: str = Field("核心概念", description="分类: 核心概念/定理/方法/现象")
    chapter: str = Field("", description="所在章节标题")
    chapter_id: str = Field("", description="章节ID")
    page: int = Field(0, description="页码")
    textbook_id: str = Field("", description="教材ID")
    frequency: int = Field(1, description="出现频次")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "node_001",
                "name": "动作电位",
                "definition": "细胞受到刺激后，膜电位发生的一次快速而可逆的倒转",
                "category": "核心概念",
                "chapter": "第二章 细胞的基本功能",
                "chapter_id": "ch_02",
                "page": 35,
                "textbook_id": "生理学",
                "frequency": 1
            }
        }


class KnowledgeRelation(BaseModel):
    source: str = Field(..., description="源节点ID")
    target: str = Field(..., description="目标节点ID")
    relation_type: str = Field(..., description="关系类型: prerequisite/parallel/contains/applies_to")
    description: str = Field("", description="关系描述")
    confidence: float = Field(1.0, description="置信度")

    class Config:
        json_schema_extra = {
            "example": {
                "source": "node_001",
                "target": "node_002",
                "relation_type": "prerequisite",
                "description": "理解动作电位需要先掌握静息电位的概念",
                "confidence": 0.95
            }
        }


class KnowledgeGraph(BaseModel):
    textbook_id: str = Field(..., description="教材ID")
    textbook_title: str = Field("", description="教材标题")
    nodes: List[KnowledgeNode] = Field(default_factory=list, description="知识点节点列表")
    relations: List[KnowledgeRelation] = Field(default_factory=list, description="关系列表")
    extracted_at: Optional[datetime] = Field(None, description="提取时间")
    total_nodes: int = Field(0, description="节点总数")
    total_relations: int = Field(0, description="关系总数")

    class Config:
        json_schema_extra = {
            "example": {
                "textbook_id": "生理学",
                "textbook_title": "生理学",
                "nodes": [],
                "relations": [],
                "extracted_at": "2024-01-01T00:00:00",
                "total_nodes": 0,
                "total_relations": 0
            }
        }


class ExtractionTaskStatus(BaseModel):
    file_id: str = Field(..., description="文件ID")
    status: ExtractionStatus = Field(ExtractionStatus.PENDING, description="提取状态")
    progress: float = Field(0.0, description="进度百分比")
    current_chapter: str = Field("", description="当前处理章节")
    error_message: Optional[str] = Field(None, description="错误信息")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")


__all__ = [
    "ExtractionStatus",
    "KnowledgeNode",
    "KnowledgeRelation",
    "KnowledgeGraph",
    "ExtractionTaskStatus",
]

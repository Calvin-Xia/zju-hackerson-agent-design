"""应用配置。

所有配置项均可通过环境变量或 ``.env`` 文件覆盖。

列表类型的配置以**字符串**形式存储，同时支持 JSON 数组和逗号分隔两种写法，
再通过属性（``settings.cors_origins`` / ``settings.allowed_extensions``）取到列表：

```env
ALLOWED_EXTENSIONS=pdf,md,txt
ALLOWED_EXTENSIONS=["pdf", "md", "txt"]
```

之所以不直接声明成 ``List[str]``：pydantic-settings 对复杂类型会先用
``json.loads`` 解码 ``.env`` 里的原始值，逗号分隔写法会在拿到字段校验器之前
就抛 ``SettingsError``，导致 ``cp .env.example .env`` 之后服务直接起不来。
"""

from pathlib import Path
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_list(value: object) -> List[str]:
    """把逗号分隔字符串或 JSON 数组字符串解析成列表。"""
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            import json

            try:
                parsed = json.loads(stripped)
            except ValueError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
            return []
        return [item.strip() for item in stripped.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---------- 服务 ----------
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    DATA_DIR: str = "data"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:5174"

    # ---------- LLM ----------
    DASHSCOPE_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    LLM_PROVIDER: str = "dashscope"
    # 留空则使用各提供商的默认模型
    LLM_MODEL: str = ""
    LLM_TIMEOUT: float = 90.0
    # 额外重试次数（实际请求次数 = 该值 + 1）
    LLM_MAX_RETRIES: int = 3
    LLM_CONCURRENCY: int = 4

    # ---------- 嵌入 ----------
    # auto | sentence-transformers | hashing
    EMBEDDING_BACKEND: str = "auto"
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIM: int = 384
    # 离线环境下跳过 sentence-transformers 的网络重试，直接使用本地/降级方案
    EMBEDDING_OFFLINE: bool = True

    # ---------- 向量库 ----------
    VECTOR_DB: str = "faiss"
    # 向量库根目录（其下按索引名分目录，例如 default/vectors.npy）
    VECTOR_DB_PATH: str = "data/vectorstore"

    # ---------- 上传 ----------
    MAX_UPLOAD_SIZE_MB: int = 200
    ALLOWED_EXTENSIONS: str = "pdf,md,txt,docx,xlsx"

    # ---------- 知识点抽取 ----------
    EXTRACTION_MAX_CHARS: int = 6000
    # 抽取到的知识点少于该数量时视为抽取失败
    EXTRACTION_MIN_NODES: int = 1

    # ---------- 语义对齐 ----------
    # 进入候选对的嵌入相似度阈值
    ALIGNMENT_THRESHOLD: float = 0.72
    # 达到该相似度直接判定等价，无需 LLM 复核
    ALIGNMENT_HIGH_CONFIDENCE: float = 0.88
    # 是否使用 LLM 复核灰色区间的候选对（较慢，默认关闭）
    ALIGNMENT_USE_LLM: bool = False
    # 单次整合中 LLM 复核的候选对数量上限
    ALIGNMENT_LLM_MAX_PAIRS: int = 50

    # ---------- 压缩比控制 ----------
    # 整合后字数 / 原始总字数，要求 <= 30%
    MAX_COMPRESSION_RATIO: float = 0.30
    # 是否允许通过压缩知识点描述（抽取式摘要）来达成目标
    COMPRESSION_CONDENSE: bool = True
    # 描述短于该字数时视为已足够精炼，不做摘要（避免把一句话截断成病句）
    COMPRESSION_MIN_KEEP_CHARS: int = 60
    # 摘要结果的下限字数
    COMPRESSION_MIN_DEFINITION_CHARS: int = 30

    # ---------- RAG ----------
    CHUNK_SIZE: int = 600
    CHUNK_OVERLAP: int = 100
    TOP_K: int = 5
    # 召回候选数量（先多召回，再阈值过滤/去重）
    RAG_RECALL_K: int = 20
    # 低于该相似度的片段视为不相关；留空则按嵌入后端自动选择
    RAG_MIN_SCORE: Optional[float] = None
    # 自适应阈值：不低于最高分 × 该比例（避免只召回一个片段）
    RAG_RELATIVE_SCORE_RATIO: float = 0.45
    # 拼进 Prompt 的上下文总字数上限
    RAG_MAX_CONTEXT_CHARS: int = 6000
    # 同一教材最多使用的片段数，保证来源多样性
    RAG_MAX_CHUNKS_PER_TEXTBOOK: int = 3

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    @field_validator("RAG_MIN_SCORE", mode="before")
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        """``RAG_MIN_SCORE=``（留空）应当表示"自动选择"，而不是解析失败。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    # ------------------------------------------------------------------
    # 派生属性
    # ------------------------------------------------------------------
    @property
    def cors_origins(self) -> List[str]:
        return _split_list(self.CORS_ORIGINS)

    @property
    def allowed_extensions(self) -> List[str]:
        return sorted({ext.lower().lstrip(".") for ext in _split_list(self.ALLOWED_EXTENSIONS) if ext})

    @property
    def data_dir(self) -> Path:
        return Path(self.DATA_DIR)

    @property
    def textbooks_dir(self) -> Path:
        return self.data_dir / "textbooks"

    @property
    def knowledge_graphs_dir(self) -> Path:
        return self.data_dir / "knowledge_graphs"


settings = Settings()

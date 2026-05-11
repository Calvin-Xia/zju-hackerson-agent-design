import os
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"]

    DASHSCOPE_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    LLM_PROVIDER: str = "dashscope"

    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"

    VECTOR_DB: str = "faiss"
    VECTOR_DB_PATH: str = "./vector_data"

    MAX_UPLOAD_SIZE_MB: int = 200
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "md", "txt", "docx"]

    CHUNK_SIZE: int = 600
    CHUNK_OVERLAP: int = 100
    TOP_K: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()

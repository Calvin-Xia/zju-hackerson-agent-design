"""应用入口。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.router import api_router
from src.api.routes.kg import rebuild_extraction_status_from_files
from src.api.routes.parse import rebuild_parse_status_from_files
from src.embedding.service import get_embedding_service
from src.parsers import docx_parser, markdown_parser, pdf_parser, txt_parser, xlsx_parser  # noqa: F401
from src.shared.config import settings
from src.vectorstore.faiss_store import get_vector_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

FRONTEND_DIST = Path("frontend/dist")


def _bootstrap() -> None:
    """启动时的同步初始化（放到子线程执行，避免阻塞事件循环）。"""
    settings.textbooks_dir.mkdir(parents=True, exist_ok=True)
    rebuild_parse_status_from_files()
    rebuild_extraction_status_from_files()

    try:
        embedding_service = get_embedding_service()
        vector_store = get_vector_store()
        loaded = vector_store.load("default", expected_signature=embedding_service.signature)
        if loaded:
            logger.info(
                "已加载向量索引：%d 个片段（后端 %s）",
                vector_store.size, embedding_service.backend,
            )
        else:
            logger.info(
                "没有可用的向量索引（嵌入后端 %s），需要重新建立索引",
                embedding_service.backend,
            )
    except Exception as exc:  # 索引加载失败不应阻止服务启动
        logger.warning("加载向量索引失败: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("服务启动中…")
    await asyncio.to_thread(_bootstrap)
    logger.info("服务已就绪")
    yield
    logger.info("服务关闭")


app = FastAPI(
    title="学科知识整合智能体",
    description="AI全栈极速黑客松赛题 - 浙江大学未来学习中心·AI生态 2026",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins = settings.cors_origins
_allow_credentials = "*" not in _cors_origins
if not _allow_credentials:
    # 浏览器规范不允许 allow_origins=["*"] 与 allow_credentials=True 同时生效
    logger.warning("CORS_ORIGINS 含通配符 *，已关闭 allow_credentials 以避免请求被浏览器拒绝")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("未处理异常 %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})


@app.get("/api/health")
async def health_check():
    """健康检查（含依赖状态，便于部署探活）。"""
    vector_store = get_vector_store()
    try:
        embedding_service = get_embedding_service()
        embedding_info = {
            "backend": embedding_service.backend,
            "dimension": embedding_service.dimension,
        }
    except Exception as exc:
        embedding_info = {"backend": "unavailable", "error": str(exc)}

    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "llm_provider": settings.LLM_PROVIDER,
        "embedding": embedding_info,
        "vector_store": {
            "chunks": vector_store.size,
            "dimension": vector_store.dimension or 0,
            "signature": vector_store.embedding_signature,
        },
    }


# ----------------------------------------------------------------------
# 生产模式下托管前端构建产物（开发时由 Vite 代理）
# ----------------------------------------------------------------------
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "接口不存在"})
        candidate = FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

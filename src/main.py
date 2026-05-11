import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.router import api_router
from src.shared.config import settings
from src.parsers import pdf_parser, markdown_parser, txt_parser, docx_parser
from src.kg import extractor
from src.api.routes.parse import rebuild_parse_status_from_files
from src.api.routes.kg import rebuild_extraction_status_from_files

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up...")
    data_dir = Path("data/textbooks")
    data_dir.mkdir(parents=True, exist_ok=True)
    rebuild_parse_status_from_files()
    rebuild_extraction_status_from_files()
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="学科知识整合智能体",
    description="AI全栈极速黑客松赛题 - 浙江大学未来学习中心·AI生态 2026",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

from fastapi import APIRouter

from src.api.routes import upload, files

api_router = APIRouter()

api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(files.router, prefix="/files", tags=["files"])

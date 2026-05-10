from fastapi import APIRouter

from src.api.routes import upload, files, parse

api_router = APIRouter()

api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(parse.router, prefix="/parse", tags=["parse"])

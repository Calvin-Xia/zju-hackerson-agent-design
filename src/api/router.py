from fastapi import APIRouter

from src.api.routes import upload, files, parse, kg

api_router = APIRouter()

api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(parse.router, prefix="/parse", tags=["parse"])
api_router.include_router(kg.router, prefix="/kg", tags=["knowledge-graph"])

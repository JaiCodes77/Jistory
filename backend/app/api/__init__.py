from fastapi import APIRouter

from app.api import health
from app.imports import router as import_router

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(import_router)

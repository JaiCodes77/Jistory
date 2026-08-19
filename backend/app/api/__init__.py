from fastapi import APIRouter

from app.api import health
from app.ask import router as ask_router
from app.conversations import router as conversations_router
from app.dashboard import router as dashboard_router
from app.graph import router as graph_router
from app.imports import router as import_router
from app.search import router as search_router
from app.user_settings import router as settings_router

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(import_router)
api_router.include_router(conversations_router)
api_router.include_router(graph_router)
api_router.include_router(search_router)
api_router.include_router(ask_router)
api_router.include_router(dashboard_router)
api_router.include_router(settings_router)

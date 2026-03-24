"""API package — routers assembled here."""
from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.stats import router as stats_router
from app.api.v1.items import router as items_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(stats_router, prefix="/stats", tags=["stats"])
api_router.include_router(items_router, prefix="/v1/items", tags=["items"])

__all__ = ["api_router"]

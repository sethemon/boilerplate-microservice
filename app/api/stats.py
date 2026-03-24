"""
Stats / metrics endpoints.

GET /stats           — request counters and uptime
GET /stats/system    — CPU, memory, open file descriptors
"""
from __future__ import annotations

import platform
import sys
from typing import Any

import psutil
from fastapi import APIRouter, Request

from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.get("", summary="Request statistics")
async def request_stats(request: Request) -> dict[str, Any]:
    """Return aggregated request counts, error rates, per-endpoint timings."""
    app_stats = getattr(request.app.state, "stats", None)
    if app_stats is None:
        return {"error": "stats not initialised"}
    return app_stats.snapshot()


@router.get("/system", summary="System resource usage")
async def system_stats() -> dict[str, Any]:
    """CPU, memory, and process info."""
    proc = psutil.Process()
    mem = proc.memory_info()
    return {
        "service": {
            "name": settings.app.name,
            "version": settings.app.version,
            "environment": settings.app.environment,
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
        },
        "process": {
            "pid": proc.pid,
            "cpu_percent": proc.cpu_percent(interval=0.1),
            "memory_rss_mb": round(mem.rss / 1024 / 1024, 2),
            "memory_vms_mb": round(mem.vms / 1024 / 1024, 2),
            "open_files": len(proc.open_files()),
            "threads": proc.num_threads(),
        },
        "host": {
            "cpu_count": psutil.cpu_count(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_total_mb": round(psutil.virtual_memory().total / 1024 / 1024, 2),
            "memory_available_mb": round(psutil.virtual_memory().available / 1024 / 1024, 2),
            "memory_percent": psutil.virtual_memory().percent,
        },
    }


@router.get("/info", summary="Service information")
async def service_info() -> dict[str, Any]:
    """Static service metadata."""
    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "description": settings.app.description,
        "environment": settings.app.environment,
    }

"""
Health-check endpoints.

GET /health          — lightweight liveness probe (no external calls)
GET /health/ready    — readiness probe: checks DB + RabbitMQ
GET /health/db       — database connectivity detail
GET /health/queue    — RabbitMQ connectivity detail
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.db.session import check_db_health
from app.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.get(
    "",
    summary="Liveness probe",
    response_description="Returns 200 if the process is alive",
)
async def liveness() -> dict[str, str]:
    """Lightweight liveness check — no external calls."""
    return {"status": "alive"}


@router.get(
    "/ready",
    summary="Readiness probe",
    response_description="Returns 200 if all dependencies are reachable",
)
async def readiness(request: Request) -> JSONResponse:
    """
    Readiness check — verifies DB and RabbitMQ connections.
    Returns 200 only when all checks pass; 503 otherwise.
    """
    checks: dict[str, Any] = {}
    healthy = True

    # Database
    db_result = await check_db_health()
    checks["database"] = db_result
    if db_result["status"] != "healthy":
        healthy = False

    # RabbitMQ — read from app.state (set in lifespan)
    producer = getattr(request.app.state, "producer", None)
    if producer is not None:
        mq_ok = producer.is_connected
        checks["rabbitmq"] = {"status": "healthy" if mq_ok else "unhealthy"}
        if not mq_ok:
            healthy = False
    else:
        checks["rabbitmq"] = {"status": "not_configured"}

    http_status = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
        status_code=http_status,
    )


@router.get("/db", summary="Database health detail")
async def db_health() -> dict[str, str]:
    """Detailed database connectivity check."""
    return await check_db_health()


@router.get("/queue", summary="RabbitMQ health detail")
async def queue_health(request: Request) -> dict[str, Any]:
    """RabbitMQ connectivity check."""
    producer = getattr(request.app.state, "producer", None)
    if producer is None:
        return {"status": "not_configured"}
    connected = producer.is_connected
    return {
        "status": "healthy" if connected else "unhealthy",
        "url": settings_host_only(),
    }


def settings_host_only() -> str:
    from app.config import settings
    url = settings.rabbitmq.url
    # Return only the host part, not credentials
    try:
        return url.split("@")[-1]
    except Exception:
        return "unknown"

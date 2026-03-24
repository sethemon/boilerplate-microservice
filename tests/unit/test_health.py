"""Tests for /api/health endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


pytestmark = pytest.mark.asyncio


async def test_liveness(client: AsyncClient) -> None:
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


async def test_readiness_with_healthy_db(client: AsyncClient) -> None:
    with patch("app.api.health.check_db_health", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {"status": "healthy", "detail": "DB reachable"}
        resp = await client.get("/api/health/ready")
    # Producer mock is connected → both checks pass
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"]["status"] == "healthy"


async def test_readiness_unhealthy_db(client: AsyncClient) -> None:
    with patch("app.api.health.check_db_health", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {"status": "unhealthy", "detail": "Connection refused"}
        resp = await client.get("/api/health/ready")
    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"


async def test_db_health_endpoint(client: AsyncClient) -> None:
    with patch("app.api.health.check_db_health", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {"status": "healthy", "detail": "DB reachable"}
        resp = await client.get("/api/health/db")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


async def test_queue_health_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/api/health/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("healthy", "unhealthy", "not_configured")


async def test_queue_health_not_configured(client: AsyncClient) -> None:
    """When producer is not set on app.state, returns not_configured."""
    # Temporarily remove producer
    del client._transport.app.state.producer  # type: ignore[attr-defined]
    resp = await client.get("/api/health/queue")
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_configured"

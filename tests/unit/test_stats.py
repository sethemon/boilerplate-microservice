"""Tests for /api/stats endpoints and the AppStats class."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.middleware.logging_middleware import AppStats

pytestmark = pytest.mark.asyncio


# ── Unit tests for AppStats ───────────────────────────────────────────────────

def test_app_stats_initial_state() -> None:
    stats = AppStats()
    snap = stats.snapshot()
    assert snap["total_requests"] == 0
    assert snap["total_success"] == 0
    assert snap["total_errors"] == 0
    assert snap["error_rate"] == 0.0


def test_app_stats_records_success() -> None:
    stats = AppStats()
    stats.record("/api/items", 200, 10.0)
    stats.record("/api/items", 201, 5.0)
    snap = stats.snapshot()
    assert snap["total_requests"] == 2
    assert snap["total_success"] == 2
    assert snap["total_errors"] == 0
    assert snap["endpoints"]["/api/items"]["avg_duration_ms"] == 7.5


def test_app_stats_records_errors() -> None:
    stats = AppStats()
    stats.record("/api/items", 500, 1.0)
    snap = stats.snapshot()
    assert snap["total_errors"] == 1
    assert snap["error_rate"] == 1.0


def test_app_stats_thread_safety() -> None:
    """Hammer from multiple threads and verify final count is consistent."""
    import threading
    stats = AppStats()
    N = 100

    def worker():
        for _ in range(N):
            stats.record("/path", 200, 1.0)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert stats.snapshot()["total_requests"] == N * 10


# ── Integration tests against HTTP endpoints ──────────────────────────────────

async def test_stats_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_requests" in body
    assert "uptime_seconds" in body


async def test_system_stats_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/api/stats/system")
    assert resp.status_code == 200
    body = resp.json()
    assert "process" in body
    assert "host" in body
    assert "runtime" in body


async def test_info_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/api/stats/info")
    assert resp.status_code == 200
    body = resp.json()
    assert "name" in body
    assert "version" in body

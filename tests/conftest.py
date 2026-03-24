"""
Pytest configuration and shared fixtures.

Strategy
────────
* All tests use an in-memory SQLite database (aiosqlite) — zero config,
  zero external dependencies, fast.
* The FastAPI app is overridden at the database dependency level so routes
  use the test DB without any code changes.
* RabbitMQ is mocked — no broker needed in CI.
* Each test gets a fresh, isolated DB (tables dropped + recreated).
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ── Force SQLite for all tests ────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Patch config BEFORE app imports so create_async_engine picks up the test URL
import app.config as _cfg_module
_cfg_module.settings.database.url = TEST_DATABASE_URL


# ── Now import app (after config patch) ──────────────────────────────────────
from app.db.base import Base
from app.db.session import get_db_dependency
from app.main import create_app

# ── Pytest async mode ─────────────────────────────────────────────────────────
pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ── Per-test async DB engine + session ───────────────────────────────────────

@pytest_asyncio.fixture()
async def test_engine():
    """Fresh in-memory SQLite engine per test."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        import app.db.models  # noqa: F401 — register all models
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a test DB session that rolls back after each test."""
    session_factory = async_sessionmaker(
        bind=test_engine, expire_on_commit=False, autoflush=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


# ── Mocked RabbitMQ producer ─────────────────────────────────────────────────

@pytest.fixture()
def mock_producer():
    producer = MagicMock()
    producer.is_connected = True
    producer.connect = AsyncMock()
    producer.close = AsyncMock()
    producer.publish = AsyncMock()
    return producer


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def client(db_session: AsyncSession, mock_producer) -> AsyncGenerator[AsyncClient, None]:
    """
    Async test client with:
      * DB dependency overridden to use the test session
      * RabbitMQ producer replaced with a mock
      * Consumer task disabled (no broker needed)
    """
    app = create_app()

    # Override DB dependency
    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db_dependency] = _override_db

    # Inject mock producer & skip consumer
    app.state.producer = mock_producer
    app.state.consumer = MagicMock()

    # Attach stats
    from app.middleware.logging_middleware import AppStats
    app.state.stats = AppStats()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

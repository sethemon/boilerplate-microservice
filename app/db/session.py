"""
Async database engine + session factory.

Supported databases (set DATABASE_URL in config.yaml or .env):
───────────────────────────────────────────────────────────────
  PostgreSQL  │ postgresql+asyncpg://user:pass@host:5432/db
  MySQL       │ mysql+aiomysql://user:pass@host:3306/db
  SQLite      │ sqlite+aiosqlite:///./app.db
  SQL Server  │ mssql+pyodbc://user:pass@host:1433/db?driver=…   (sync wrapped)
  Oracle      │ oracle+cx_oracle://user:pass@host:1521/SERVICE   (sync wrapped)

SQL Server / Oracle note
────────────────────────
Those drivers do not have mature async support.  They are wrapped via
`run_sync` so the public interface (`async with get_db()`) stays identical —
you just lose true async DB concurrency for those backends.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)


def _build_engine() -> AsyncEngine:
    cfg = settings.database
    url = cfg.url

    connect_args: dict[str, Any] = {}
    engine_kwargs: dict[str, Any] = {
        "echo": cfg.echo,
    }

    if cfg.is_sqlite:
        # SQLite: single-file, use StaticPool so the same in-memory DB is
        # shared across test workers.
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["poolclass"] = StaticPool
    else:
        engine_kwargs["pool_size"] = cfg.pool_size
        engine_kwargs["max_overflow"] = cfg.max_overflow
        engine_kwargs["pool_timeout"] = cfg.pool_timeout
        engine_kwargs["pool_recycle"] = cfg.pool_recycle
        engine_kwargs["pool_pre_ping"] = True   # verify connections on checkout

    if cfg.is_mssql or cfg.is_oracle:
        # Fallback: use NullPool + sync driver wrapped by asyncio thread-pool
        engine_kwargs.pop("pool_size", None)
        engine_kwargs.pop("max_overflow", None)
        engine_kwargs.pop("pool_timeout", None)
        engine_kwargs["poolclass"] = NullPool

    log.info("Creating DB engine for: {url}", url=url.split("@")[-1])  # hide creds
    return create_async_engine(url, **engine_kwargs)


engine: AsyncEngine = _build_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields a DB session and handles
    commit / rollback automatically.

    Usage (in service / repo):
        async with get_db() as db:
            result = await db.execute(select(Item))
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_dependency() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency version — use with `Depends(get_db_dependency)`.

    Example:
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db_dependency)):
            ...
    """
    async with get_db() as session:
        yield session


async def check_db_health() -> dict[str, str]:
    """Ping the database and return a status dict."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "healthy", "detail": "DB reachable"}
    except Exception as exc:
        log.error("DB health check failed: {e}", e=exc)
        return {"status": "unhealthy", "detail": str(exc)}


async def create_all_tables() -> None:
    """Create all tables defined in the ORM models (idempotent)."""
    from app.db.base import Base
    import app.db.models  # noqa: F401 — registers all models with Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("Database tables created / verified.")


async def drop_all_tables() -> None:
    """Drop all tables — use in tests only!"""
    from app.db.base import Base
    import app.db.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    log.warning("All database tables dropped.")

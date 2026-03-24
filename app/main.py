"""
Application entry point.

Run locally:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Or via the console-script (setup.cfg [options.entry_points]):
    microservice

Build and run with Docker:
    docker compose up --build
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)


# ── lifespan (startup + shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Code before `yield` runs at startup; code after runs at shutdown.
    All shared resources (DB engine, MQ connections) are managed here.
    """
    log.info("Starting up '{name}' v{ver}", name=settings.app.name, ver=settings.app.version)

    # ── Initialise stats ──────────────────────────────────────────────────────
    from app.middleware.logging_middleware import AppStats
    app.state.stats = AppStats()

    # ── Database ──────────────────────────────────────────────────────────────
    from app.db.session import create_all_tables, engine
    await create_all_tables()
    log.info("Database ready")

    # ── RabbitMQ producer ─────────────────────────────────────────────────────
    from app.messaging.producer import MessageProducer
    producer = MessageProducer()
    try:
        await producer.connect()
        app.state.producer = producer
        log.info("RabbitMQ producer connected")
    except Exception as exc:
        log.warning("RabbitMQ unavailable at startup (continuing): {e}", e=exc)
        app.state.producer = producer  # still attach — health check will report unhealthy

    # ── RabbitMQ consumer (background task) ───────────────────────────────────
    from app.messaging.consumer import MessageConsumer
    consumer = MessageConsumer()
    app.state.consumer = consumer
    consumer_task = asyncio.create_task(_run_consumer(consumer), name="mq-consumer")

    # ── Register example message handlers ─────────────────────────────────────
    import app.messaging.handlers  # noqa: F401 — ensures @on decorators execute

    log.info("Startup complete")
    yield  # ←── application runs here ──────────────────────────────────────

    # ── Shutdown ──────────────────────────────────────────────────────────────
    log.info("Shutting down ...")
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await consumer.stop()
    await producer.close()
    await engine.dispose()
    log.info("Shutdown complete")


async def _run_consumer(consumer) -> None:  # type: ignore[no-untyped-def]
    """Wrapper so consumer exceptions are logged, not silently swallowed."""
    try:
        await consumer.start()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        log.error("Consumer task exited with error: {e}", e=exc)


# ── FastAPI application ────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app.name,
        description=settings.app.description,
        version=settings.app.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request logging + stats ───────────────────────────────────────────────
    from app.middleware.logging_middleware import RequestLoggingMiddleware
    app.add_middleware(RequestLoggingMiddleware)

    # ── Routers ───────────────────────────────────────────────────────────────
    from app.api import api_router
    app.include_router(api_router, prefix="/api")

    # ── Prometheus metrics ────────────────────────────────────────────────────
    if settings.metrics.enabled:
        try:
            from prometheus_client import make_asgi_app
            from starlette.routing import Mount
            metrics_app = make_asgi_app()
            app.mount(settings.metrics.path, metrics_app)
        except ImportError:
            log.warning("prometheus_client not installed; /metrics disabled")

    # ── Root endpoint ─────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse({
            "service": settings.app.name,
            "version": settings.app.version,
            "docs": "/docs",
            "health": "/api/health",
        })

    return app


app: FastAPI = create_app()


def run() -> None:
    """Console-script entry point."""
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        workers=settings.app.workers,
        log_level=settings.logging.level.lower(),
        reload=settings.app.debug,
    )


if __name__ == "__main__":
    run()

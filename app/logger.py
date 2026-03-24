"""
Thread-safe, async-safe Loguru logger.

Key design decisions
────────────────────
* `enqueue=True`  → all log records are sent through an internal multiprocessing
  queue, so writes happen in a dedicated background thread.  Worker threads and
  asyncio tasks never block on I/O; they also never interleave partial lines.
* A custom `InterceptHandler` redirects Python's stdlib `logging` (used by
  uvicorn, SQLAlchemy, aio-pika …) into Loguru so every library writes to the
  same sinks.
* `diagnose=False` in production hides local-variable values from tracebacks
  (prevents accidental secret leakage).

Usage
─────
    from app.logger import get_logger
    log = get_logger(__name__)
    log.info("hello {name}", name="world")
    log.bind(request_id="abc").info("scoped message")
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from app.config import settings

if TYPE_CHECKING:
    from loguru import Logger


# ── redirect stdlib logging → loguru ─────────────────────────────────────────

class _InterceptHandler(logging.Handler):
    """Forward all stdlib log records to Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        # find the corresponding Loguru level
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # walk up the call stack until we leave logging internals
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _setup_logger() -> None:
    cfg = settings.logging

    # Ensure log directory exists
    log_file = Path(cfg.file_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Remove default sink
    logger.remove()

    shared = dict(
        format=cfg.format,
        enqueue=cfg.enqueue,          # ← the thread-safety magic
        backtrace=cfg.backtrace,
        diagnose=cfg.diagnose,
    )

    # Console sink
    logger.add(
        sys.stdout,
        level=cfg.level,
        colorize=True,
        **shared,
    )

    # Rotating file sink
    logger.add(
        str(log_file),
        level=cfg.level,
        rotation=cfg.rotation,
        retention=cfg.retention,
        compression=cfg.compression,
        **shared,
    )

    # Redirect stdlib logging
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "aio_pika", "aiormq"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_setup_logger()


def get_logger(name: str) -> "Logger":
    """Return a context-bound logger for the given module name."""
    return logger.bind(logger_name=name)

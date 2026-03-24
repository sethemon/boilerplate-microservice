"""
Request / response logging middleware + stats collection.

Attaches a unique `X-Request-ID` to every request and records:
  * method, path, status_code, duration_ms
  * Per-endpoint counters stored on app.state.stats
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.logger import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


@dataclass
class EndpointStats:
    total: int = 0
    success: int = 0
    errors: int = 0
    total_duration_ms: float = 0.0

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.total if self.total else 0.0


@dataclass
class AppStats:
    """Thread-safe application-wide request statistics."""
    _lock: Lock = field(default_factory=Lock, repr=False)
    total_requests: int = 0
    total_success: int = 0
    total_errors: int = 0
    endpoints: dict[str, EndpointStats] = field(default_factory=lambda: defaultdict(EndpointStats))
    start_time: float = field(default_factory=time.time)

    def record(self, path: str, status_code: int, duration_ms: float) -> None:
        key = path
        success = status_code < 400
        with self._lock:
            self.total_requests += 1
            if success:
                self.total_success += 1
            else:
                self.total_errors += 1
            ep = self.endpoints[key]
            ep.total += 1
            ep.total_duration_ms += duration_ms
            if success:
                ep.success += 1
            else:
                ep.errors += 1

    def snapshot(self) -> dict:
        with self._lock:
            uptime = time.time() - self.start_time
            return {
                "uptime_seconds": round(uptime, 2),
                "total_requests": self.total_requests,
                "total_success": self.total_success,
                "total_errors": self.total_errors,
                "error_rate": round(self.total_errors / max(self.total_requests, 1), 4),
                "endpoints": {
                    k: {
                        "total": v.total,
                        "success": v.success,
                        "errors": v.errors,
                        "avg_duration_ms": round(v.avg_duration_ms, 2),
                    }
                    for k, v in self.endpoints.items()
                },
            }


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request/response and update AppStats."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start = time.perf_counter()

        # Bind request context to this log chain
        with log.contextualize(request_id=request_id):
            log.info(
                "→ {method} {path}",
                method=request.method,
                path=request.url.path,
            )
            try:
                response = await call_next(request)
            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                log.exception(
                    "✗ {method} {path} 500 {dur:.1f}ms",
                    method=request.method,
                    path=request.url.path,
                    dur=duration_ms,
                )
                # record error
                if hasattr(request.app.state, "stats"):
                    request.app.state.stats.record(request.url.path, 500, duration_ms)
                raise

            duration_ms = (time.perf_counter() - start) * 1000
            log.info(
                "← {method} {path} {status} {dur:.1f}ms",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                dur=duration_ms,
            )

            if hasattr(request.app.state, "stats"):
                request.app.state.stats.record(
                    request.url.path, response.status_code, duration_ms
                )

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            return response

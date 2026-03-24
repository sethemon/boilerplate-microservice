"""
Global message handler registry.

Register handlers with @on("routing.key.pattern") and they will be invoked
by the consumer's fallback dispatch when no per-consumer handler matches.

Example
───────
    # In your feature module (e.g. app/services/item_event_handler.py):

    from app.messaging.handlers import on

    @on("microservice.item.created")
    async def handle_item_created(body: dict) -> None:
        item_id = body["item_id"]
        # … process event …

Then import the module at startup so the decorator runs:

    # app/main.py  lifespan:
    import app.services.item_event_handler  # noqa: F401
"""
from __future__ import annotations

import fnmatch
from collections.abc import Callable, Awaitable
from typing import Any

from app.logger import get_logger

log = get_logger(__name__)

_REGISTRY: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}


def on(routing_key_pattern: str) -> Callable:
    """Decorator: register an async function for a routing key pattern."""
    def decorator(fn: Callable[[dict[str, Any]], Awaitable[None]]) -> Callable:
        _REGISTRY[routing_key_pattern] = fn
        log.debug("Registered handler '{fn}' for '{p}'", fn=fn.__name__, p=routing_key_pattern)
        return fn
    return decorator


async def dispatch(routing_key: str, body: dict[str, Any]) -> None:
    """Find the best matching handler and invoke it."""
    for pattern, handler in _REGISTRY.items():
        if fnmatch.fnmatch(routing_key, pattern):
            log.debug("Dispatching rk={rk} → {fn}", rk=routing_key, fn=handler.__name__)
            await handler(body)
            return
    log.warning("No handler registered for routing_key={rk}", rk=routing_key)


# ── built-in example handlers ─────────────────────────────────────────────────

@on("microservice.item.created")
async def _on_item_created(body: dict[str, Any]) -> None:
    log.info("EVENT item.created → item_id={id}", id=body.get("item_id"))


@on("microservice.item.deleted")
async def _on_item_deleted(body: dict[str, Any]) -> None:
    log.info("EVENT item.deleted → item_id={id}", id=body.get("item_id"))

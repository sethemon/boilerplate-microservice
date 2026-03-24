"""
Async RabbitMQ consumer using aio-pika.

Architecture
────────────
* One robust connection (auto-reconnect on broker restart).
* Configurable prefetch so slow handlers don't pile up un-acked messages.
* Per-message error handling: nack + requeue on transient errors, dead-letter
  on persistent failures.
* Dispatches messages to registered handlers by routing key pattern.

Usage
─────
    consumer = MessageConsumer()

    # register handlers BEFORE connecting
    @consumer.handler("microservice.item.*")
    async def on_item_event(body: dict, message: AbstractIncomingMessage) -> None:
        print(body)

    await consumer.start()          # blocks — run as an asyncio task
    await consumer.stop()
"""
from __future__ import annotations

import asyncio
import fnmatch
import json
from collections.abc import Callable, Awaitable
from typing import Any

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.logger import get_logger
from app.messaging.handlers import dispatch

log = get_logger(__name__)

HandlerFn = Callable[[dict[str, Any], AbstractIncomingMessage], Awaitable[None]]


class MessageConsumer:
    def __init__(self) -> None:
        self._connection: AbstractRobustConnection | None = None
        self._running = False
        self._handlers: dict[str, HandlerFn] = {}

    # ── handler registration ──────────────────────────────────────────────────

    def handler(self, routing_key_pattern: str) -> Callable[[HandlerFn], HandlerFn]:
        """
        Decorator to register a coroutine for a routing key glob pattern.

        @consumer.handler("microservice.item.*")
        async def on_item(body, msg): ...
        """
        def decorator(fn: HandlerFn) -> HandlerFn:
            self._handlers[routing_key_pattern] = fn
            log.debug("Registered handler '{fn}' for pattern '{p}'", fn=fn.__name__, p=routing_key_pattern)
            return fn
        return decorator

    # ── lifecycle ─────────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(settings.rabbitmq.max_reconnect_attempts),
        wait=wait_exponential(
            multiplier=1,
            min=settings.rabbitmq.reconnect_delay,
            max=60,
        ),
        reraise=True,
    )
    async def start(self) -> None:
        """Connect, declare topology, and start consuming (runs until stop())."""
        cfg = settings.rabbitmq
        log.info("Consumer connecting to RabbitMQ: {url}", url=cfg.url.split("@")[-1])

        self._connection = await aio_pika.connect_robust(cfg.url)
        async with self._connection:
            channel = await self._connection.channel()
            await channel.set_qos(prefetch_count=cfg.prefetch_count)

            exchange = await channel.declare_exchange(
                cfg.exchange_name,
                ExchangeType(cfg.exchange_type),
                durable=cfg.durable,
            )
            queue = await channel.declare_queue(
                cfg.queue_name,
                durable=cfg.durable,
                arguments={"x-dead-letter-exchange": f"{cfg.exchange_name}.dlx"},
            )
            await queue.bind(exchange, routing_key=cfg.routing_key)
            log.info(
                "Consumer listening on queue '{q}' routing_key='{rk}'",
                q=cfg.queue_name,
                rk=cfg.routing_key,
            )

            self._running = True
            async with queue.iterator() as messages:
                async for message in messages:
                    if not self._running:
                        break
                    asyncio.create_task(self._handle_message(message))

    async def stop(self) -> None:
        self._running = False
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        log.info("Consumer stopped")

    # ── message dispatch ──────────────────────────────────────────────────────

    async def _handle_message(self, message: AbstractIncomingMessage) -> None:
        routing_key = message.routing_key or ""
        try:
            body: dict[str, Any] = json.loads(message.body)
        except json.JSONDecodeError as exc:
            log.error("Invalid JSON in message: {e}", e=exc)
            await message.nack(requeue=False)
            return

        handler = self._find_handler(routing_key)
        if handler:
            try:
                async with message.process():
                    await handler(body, message)
                log.debug("Processed message rk={rk}", rk=routing_key)
            except Exception as exc:
                log.exception("Handler raised for rk={rk}: {e}", rk=routing_key, e=exc)
                # message.process() already nacked on exception
        else:
            # Fallback to the global dispatch table in handlers.py
            try:
                async with message.process():
                    await dispatch(routing_key, body)
            except Exception as exc:
                log.warning("Unhandled message rk={rk}: {e}", rk=routing_key, e=exc)

    def _find_handler(self, routing_key: str) -> HandlerFn | None:
        for pattern, fn in self._handlers.items():
            if fnmatch.fnmatch(routing_key, pattern):
                return fn
        return None

    # ── health ────────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

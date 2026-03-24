"""
Async RabbitMQ producer using aio-pika.

Usage
─────
    # application startup
    producer = MessageProducer()
    await producer.connect()

    # publish
    await producer.publish(
        payload={"event": "item.created", "item_id": str(item.id)},
        routing_key="microservice.item.created",
    )

    # application shutdown
    await producer.close()

The connection is lazily (re-)established: if the broker is unavailable at
startup the first `publish` call will attempt to connect.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aio_pika
from aio_pika import ExchangeType, Message
from aio_pika.abc import AbstractRobustConnection, AbstractChannel, AbstractExchange
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.logger import get_logger

log = get_logger(__name__)


class MessageProducer:
    def __init__(self) -> None:
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None

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
    async def connect(self) -> None:
        """Open a robust (auto-reconnecting) connection to RabbitMQ."""
        cfg = settings.rabbitmq
        log.info("Producer connecting to RabbitMQ: {url}", url=cfg.url.split("@")[-1])
        self._connection = await aio_pika.connect_robust(cfg.url)
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            cfg.exchange_name,
            ExchangeType(cfg.exchange_type),
            durable=cfg.durable,
        )
        log.info("Producer connected to exchange '{ex}'", ex=cfg.exchange_name)

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            log.info("Producer connection closed")

    # ── publish ───────────────────────────────────────────────────────────────

    async def publish(
        self,
        payload: dict[str, Any],
        routing_key: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        expiration: int | None = None,       # TTL in ms
        priority: int = 0,
    ) -> None:
        """
        Serialise `payload` as JSON and publish it.

        Args:
            payload:     Dict to serialise to JSON.
            routing_key: Defaults to ``settings.rabbitmq.routing_key``.
            headers:     Optional AMQP message headers.
            expiration:  Message TTL in milliseconds.
            priority:    AMQP message priority (0–9).
        """
        if self._exchange is None:
            await self.connect()

        rk = routing_key or settings.rabbitmq.routing_key
        body = json.dumps(
            {**payload, "_published_at": datetime.now(tz=timezone.utc).isoformat()},
            default=str,
        ).encode()

        message = Message(
            body=body,
            content_type="application/json",
            headers=headers or {},
            priority=priority,
            expiration=str(expiration) if expiration else None,
        )

        assert self._exchange is not None
        await self._exchange.publish(message, routing_key=rk)
        log.debug("Published message routing_key={rk} size={n}B", rk=rk, n=len(body))

    # ── health ────────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return (
            self._connection is not None
            and not self._connection.is_closed
        )

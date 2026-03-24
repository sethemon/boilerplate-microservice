"""
Integration tests for the messaging layer.

* Tests that don't require a live broker use mocks.
* The @pytest.mark.integration marker can be used to skip these in CI unless
  RABBITMQ_URL is set.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from app.messaging.handlers import dispatch, _REGISTRY
from app.messaging.producer import MessageProducer

pytestmark = pytest.mark.asyncio


# ── Handler registry tests ─────────────────────────────────────────────────────

async def test_dispatch_known_routing_key() -> None:
    called = []

    from app.messaging.handlers import on

    @on("test.dispatch.key")
    async def _handler(body):
        called.append(body)

    await dispatch("test.dispatch.key", {"x": 1})
    assert called == [{"x": 1}]

    # Clean up
    del _REGISTRY["test.dispatch.key"]


async def test_dispatch_glob_pattern() -> None:
    called = []

    from app.messaging.handlers import on

    @on("test.glob.*")
    async def _glob_handler(body):
        called.append(body["k"])

    await dispatch("test.glob.anything", {"k": "hit"})
    assert "hit" in called

    del _REGISTRY["test.glob.*"]


async def test_dispatch_unknown_key_no_error() -> None:
    """Unknown routing keys should be logged but not raise."""
    await dispatch("completely.unknown.key", {})


# ── Producer unit tests ───────────────────────────────────────────────────────

async def test_producer_publish_calls_exchange() -> None:
    """Verify publish serialises payload and calls exchange.publish."""
    producer = MessageProducer()

    mock_exchange = AsyncMock()
    mock_channel = AsyncMock()
    mock_connection = MagicMock()
    mock_connection.is_closed = False
    mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
    mock_connection.channel = AsyncMock(return_value=mock_channel)

    producer._connection = mock_connection
    producer._channel = mock_channel
    producer._exchange = mock_exchange

    await producer.publish({"event": "test", "data": "hello"}, routing_key="test.key")

    mock_exchange.publish.assert_awaited_once()
    # Extract the Message that was published
    msg_arg = mock_exchange.publish.call_args[0][0]
    body = json.loads(msg_arg.body)
    assert body["event"] == "test"
    assert body["data"] == "hello"
    assert "_published_at" in body


async def test_producer_is_connected_true() -> None:
    producer = MessageProducer()
    mock_conn = MagicMock()
    mock_conn.is_closed = False
    producer._connection = mock_conn
    assert producer.is_connected is True


async def test_producer_is_connected_false_when_closed() -> None:
    producer = MessageProducer()
    mock_conn = MagicMock()
    mock_conn.is_closed = True
    producer._connection = mock_conn
    assert producer.is_connected is False


async def test_producer_is_connected_false_when_none() -> None:
    producer = MessageProducer()
    assert producer.is_connected is False


# ── Consumer dispatch tests ───────────────────────────────────────────────────

async def test_consumer_handler_registration() -> None:
    from app.messaging.consumer import MessageConsumer
    consumer = MessageConsumer()

    @consumer.handler("order.*")
    async def on_order(body, msg):
        pass

    assert "order.*" in consumer._handlers
    assert consumer._handlers["order.*"] is on_order


async def test_consumer_find_handler_glob() -> None:
    from app.messaging.consumer import MessageConsumer
    consumer = MessageConsumer()

    @consumer.handler("*.item.*")
    async def catch_all(body, msg):
        pass

    found = consumer._find_handler("microservice.item.created")
    assert found is catch_all


async def test_consumer_find_handler_none_for_no_match() -> None:
    from app.messaging.consumer import MessageConsumer
    consumer = MessageConsumer()
    assert consumer._find_handler("totally.different.key") is None

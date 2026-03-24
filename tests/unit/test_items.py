"""Tests for the /api/v1/items CRUD endpoints."""
from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/items"


# ── helpers ───────────────────────────────────────────────────────────────────

async def _create_item(client: AsyncClient, **overrides) -> dict:
    payload = {"name": "Widget", "price": 9.99, **overrides}
    resp = await client.post(BASE, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── CREATE ────────────────────────────────────────────────────────────────────

async def test_create_item_success(client: AsyncClient) -> None:
    body = await _create_item(client, name="Test Widget", price=4.99)
    assert body["name"] == "Test Widget"
    assert body["price"] == 4.99
    assert body["is_active"] is True
    assert "id" in body
    assert "created_at" in body


async def test_create_item_with_tags(client: AsyncClient) -> None:
    body = await _create_item(client, tags={"color": "red", "size": "large"})
    assert body["tags"]["color"] == "red"


async def test_create_item_missing_name_returns_422(client: AsyncClient) -> None:
    resp = await client.post(BASE, json={"price": 1.0})
    assert resp.status_code == 422


async def test_create_item_negative_price_returns_422(client: AsyncClient) -> None:
    resp = await client.post(BASE, json={"name": "x", "price": -1.0})
    assert resp.status_code == 422


# ── READ ──────────────────────────────────────────────────────────────────────

async def test_list_items_empty(client: AsyncClient) -> None:
    resp = await client.get(BASE)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_items_pagination(client: AsyncClient) -> None:
    for i in range(5):
        await _create_item(client, name=f"Item {i}")
    resp = await client.get(BASE, params={"skip": 0, "limit": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 3
    assert body["total"] == 5


async def test_list_items_name_filter(client: AsyncClient) -> None:
    await _create_item(client, name="Apple Watch")
    await _create_item(client, name="Banana Phone")
    resp = await client.get(BASE, params={"name": "apple"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all("Apple" in i["name"] for i in items)


async def test_get_item_success(client: AsyncClient) -> None:
    created = await _create_item(client)
    resp = await client.get(f"{BASE}/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


async def test_get_item_not_found(client: AsyncClient) -> None:
    resp = await client.get(f"{BASE}/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── UPDATE ────────────────────────────────────────────────────────────────────

async def test_update_item_price(client: AsyncClient) -> None:
    created = await _create_item(client, price=10.0)
    resp = await client.patch(f"{BASE}/{created['id']}", json={"price": 19.99})
    assert resp.status_code == 200
    assert resp.json()["price"] == 19.99


async def test_update_item_not_found(client: AsyncClient) -> None:
    resp = await client.patch(f"{BASE}/{uuid.uuid4()}", json={"price": 1.0})
    assert resp.status_code == 404


async def test_update_item_empty_payload_returns_error(client: AsyncClient) -> None:
    created = await _create_item(client)
    resp = await client.patch(f"{BASE}/{created['id']}", json={})
    assert resp.status_code in (400, 422, 404)


# ── DELETE ────────────────────────────────────────────────────────────────────

async def test_soft_delete_item(client: AsyncClient) -> None:
    created = await _create_item(client)
    resp = await client.delete(f"{BASE}/{created['id']}")
    assert resp.status_code == 204

    # Should not appear in the default list
    list_resp = await client.get(BASE)
    ids = [i["id"] for i in list_resp.json()["items"]]
    assert created["id"] not in ids


async def test_hard_delete_item(client: AsyncClient) -> None:
    created = await _create_item(client)
    resp = await client.delete(f"{BASE}/{created['id']}", params={"hard": "true"})
    assert resp.status_code == 204


async def test_delete_item_not_found(client: AsyncClient) -> None:
    resp = await client.delete(f"{BASE}/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── PUBLISH event ─────────────────────────────────────────────────────────────

async def test_publish_item_event(client: AsyncClient) -> None:
    created = await _create_item(client)
    resp = await client.post(f"{BASE}/{created['id']}/publish")
    assert resp.status_code == 200
    assert resp.json()["published"] is True

    # Verify producer.publish was called
    producer = client._transport.app.state.producer  # type: ignore[attr-defined]
    producer.publish.assert_awaited()


# ── Root / docs ───────────────────────────────────────────────────────────────

async def test_root_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "service" in resp.json()


async def test_openapi_schema_available(client: AsyncClient) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200

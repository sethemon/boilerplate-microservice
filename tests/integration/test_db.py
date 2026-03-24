"""
Integration tests for the database layer.

These tests run against the shared test SQLite fixture (from conftest.py)
but exercise the full repository + service stack.  They are also valid
against any other supported DB when DATABASE_URL is set in the environment.
"""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.item_repository import ItemRepository
from app.services.item_service import ItemService
from app.schemas.item import ItemCreate, ItemUpdate

pytestmark = pytest.mark.asyncio


# ── Repository-level tests ────────────────────────────────────────────────────

async def test_repo_create_and_get(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    item = await repo.create({"name": "Widget", "price": 5.0})
    assert item.id is not None

    fetched = await repo.get(item.id)
    assert fetched is not None
    assert fetched.name == "Widget"


async def test_repo_list_empty(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    items = await repo.list()
    assert list(items) == []


async def test_repo_list_with_data(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    await repo.bulk_create([{"name": f"Item {i}", "price": float(i)} for i in range(5)])
    items = await repo.list(skip=0, limit=10)
    assert len(items) == 5


async def test_repo_update(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    item = await repo.create({"name": "Old Name", "price": 1.0})
    updated = await repo.update(item.id, {"name": "New Name"})
    assert updated.name == "New Name"
    assert updated.price == 1.0  # unchanged


async def test_repo_soft_delete(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    item = await repo.create({"name": "ToDelete", "price": 0.0})
    await repo.soft_delete(item.id)

    fetched = await repo.get(item.id)
    assert fetched is not None
    assert fetched.is_deleted is True

    # Should not appear in default list
    visible = await repo.list(include_deleted=False)
    assert all(i.id != item.id for i in visible)


async def test_repo_hard_delete(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    item = await repo.create({"name": "HardDelete", "price": 0.0})
    item_id = item.id
    await repo.hard_delete(item_id)
    fetched = await repo.get(item_id)
    assert fetched is None


async def test_repo_count(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    await repo.bulk_create([{"name": f"C{i}", "price": 0.0} for i in range(3)])
    assert await repo.count() == 3


async def test_repo_find_by_name(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    await repo.create({"name": "Apple Watch", "price": 399.0})
    await repo.create({"name": "Banana Phone", "price": 99.0})
    found = await repo.find_by_name("apple")
    assert len(found) == 1
    assert found[0].name == "Apple Watch"


async def test_repo_get_not_found(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    result = await repo.get(uuid.uuid4())
    assert result is None


async def test_repo_get_or_raise(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    with pytest.raises(ValueError, match="not found"):
        await repo.get_or_raise(uuid.uuid4())


async def test_repo_exists(db_session: AsyncSession) -> None:
    repo = ItemRepository(db_session)
    item = await repo.create({"name": "X", "price": 0.0})
    assert await repo.exists(item.id) is True
    assert await repo.exists(uuid.uuid4()) is False


# ── Service-level tests ───────────────────────────────────────────────────────

async def test_service_create_and_get(db_session: AsyncSession) -> None:
    svc = ItemService(db_session)
    created = await svc.create_item(ItemCreate(name="Gadget", price=29.99))
    fetched = await svc.get_item(created.id)
    assert fetched.name == "Gadget"
    assert fetched.price == 29.99


async def test_service_update(db_session: AsyncSession) -> None:
    svc = ItemService(db_session)
    item = await svc.create_item(ItemCreate(name="Old", price=1.0))
    updated = await svc.update_item(item.id, ItemUpdate(price=99.0))
    assert updated.price == 99.0


async def test_service_soft_delete(db_session: AsyncSession) -> None:
    svc = ItemService(db_session)
    item = await svc.create_item(ItemCreate(name="Deletable", price=0.0))
    await svc.delete_item(item.id)
    result = await svc.list_items()
    assert all(i.id != item.id for i in result.items)


async def test_service_list_pagination(db_session: AsyncSession) -> None:
    svc = ItemService(db_session)
    for i in range(10):
        await svc.create_item(ItemCreate(name=f"Page Item {i}", price=float(i)))
    page1 = await svc.list_items(skip=0, limit=5)
    page2 = await svc.list_items(skip=5, limit=5)
    assert len(page1.items) == 5
    assert len(page2.items) == 5
    assert {i.id for i in page1.items}.isdisjoint({i.id for i in page2.items})

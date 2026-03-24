"""
ItemRepository — full CRUD + pagination example.

Every method accepts an `AsyncSession` so callers control the transaction
boundary (the session is never committed here; that happens in the service
layer or in the `get_db()` context manager).

READ examples
─────────────
    repo = ItemRepository(db)
    item   = await repo.get(item_id)               # by PK
    items  = await repo.list(skip=0, limit=20)     # paginated
    active = await repo.list(filters={"is_active": True})
    found  = await repo.find_by_name("Widget")

WRITE examples
──────────────
    item   = await repo.create({"name": "Widget", "price": 9.99})
    item   = await repo.update(item_id, {"price": 12.99})
    await repo.soft_delete(item_id)
    await repo.hard_delete(item_id)

BULK examples
─────────────
    items  = await repo.bulk_create([{"name": "A"}, {"name": "B"}])
    count  = await repo.count()
"""
from __future__ import annotations

import uuid
from typing import Any, Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.item import Item
from app.logger import get_logger

log = get_logger(__name__)


class ItemRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── READ ─────────────────────────────────────────────────────────────────

    async def get(self, item_id: uuid.UUID) -> Item | None:
        """Fetch a single Item by primary key. Returns None if not found."""
        return await self._db.get(Item, item_id)

    async def get_or_raise(self, item_id: uuid.UUID) -> Item:
        item = await self.get(item_id)
        if item is None:
            raise ValueError(f"Item {item_id} not found")
        return item

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> Sequence[Item]:
        """
        Paginated list with optional column-equality filters.

        Example:
            await repo.list(skip=0, limit=10, filters={"is_active": True})
        """
        stmt = select(Item)
        if not include_deleted:
            stmt = stmt.where(Item.is_deleted.is_(False))
        if filters:
            for col, val in filters.items():
                stmt = stmt.where(getattr(Item, col) == val)
        stmt = stmt.offset(skip).limit(limit).order_by(Item.created_at.desc())
        result = await self._db.execute(stmt)
        return result.scalars().all()

    async def find_by_name(self, name: str) -> Sequence[Item]:
        """Case-insensitive name search."""
        stmt = (
            select(Item)
            .where(Item.name.ilike(f"%{name}%"))
            .where(Item.is_deleted.is_(False))
        )
        result = await self._db.execute(stmt)
        return result.scalars().all()

    async def count(self, *, include_deleted: bool = False) -> int:
        stmt = select(func.count(Item.id))
        if not include_deleted:
            stmt = stmt.where(Item.is_deleted.is_(False))
        result = await self._db.execute(stmt)
        return result.scalar_one()

    # ── WRITE ────────────────────────────────────────────────────────────────

    async def create(self, data: dict[str, Any]) -> Item:
        """
        Insert a new Item and flush (gets DB-generated id without committing).

        Example:
            item = await repo.create({"name": "Widget", "price": 9.99})
        """
        item = Item(**data)
        self._db.add(item)
        await self._db.flush()
        await self._db.refresh(item)
        log.debug("Created Item id={id}", id=item.id)
        return item

    async def update(self, item_id: uuid.UUID, data: dict[str, Any]) -> Item:
        """
        Partial update — only columns present in `data` are changed.

        Example:
            item = await repo.update(item_id, {"price": 19.99, "is_active": False})
        """
        stmt = (
            update(Item)
            .where(Item.id == item_id)
            .values(**data)
            .returning(Item)
        )
        result = await self._db.execute(stmt)
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Item {item_id} not found")
        log.debug("Updated Item id={id}", id=item_id)
        return item

    async def soft_delete(self, item_id: uuid.UUID) -> None:
        """Mark item as deleted without removing the row (preferred for auditing)."""
        await self.update(item_id, {"is_deleted": True, "is_active": False})
        log.debug("Soft-deleted Item id={id}", id=item_id)

    async def hard_delete(self, item_id: uuid.UUID) -> None:
        """Permanently remove the row."""
        stmt = delete(Item).where(Item.id == item_id)
        await self._db.execute(stmt)
        log.debug("Hard-deleted Item id={id}", id=item_id)

    # ── BULK ─────────────────────────────────────────────────────────────────

    async def bulk_create(self, items_data: list[dict[str, Any]]) -> list[Item]:
        """
        Insert multiple items in one flush.

        Example:
            items = await repo.bulk_create([
                {"name": "A", "price": 1.0},
                {"name": "B", "price": 2.0},
            ])
        """
        items = [Item(**d) for d in items_data]
        self._db.add_all(items)
        await self._db.flush()
        for item in items:
            await self._db.refresh(item)
        log.debug("Bulk-created {n} items", n=len(items))
        return items

    async def exists(self, item_id: uuid.UUID) -> bool:
        stmt = select(func.count(Item.id)).where(Item.id == item_id)
        result = await self._db.execute(stmt)
        return result.scalar_one() > 0

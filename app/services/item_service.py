"""
ItemService — orchestrates the repository and any additional business logic
(validation, events, messaging …).

The service owns the session/transaction scope.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.item_repository import ItemRepository
from app.db.models.item import Item
from app.logger import get_logger
from app.schemas.item import ItemCreate, ItemListResponse, ItemRead, ItemUpdate

log = get_logger(__name__)


class ItemService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = ItemRepository(db)

    # ── queries ───────────────────────────────────────────────────────────────

    async def get_item(self, item_id: uuid.UUID) -> ItemRead:
        item = await self._repo.get_or_raise(item_id)
        return ItemRead.model_validate(item)

    async def list_items(
        self,
        skip: int = 0,
        limit: int = 100,
        name_filter: str | None = None,
    ) -> ItemListResponse:
        if name_filter:
            items = await self._repo.find_by_name(name_filter)
        else:
            items = await self._repo.list(skip=skip, limit=limit)
        total = await self._repo.count()
        return ItemListResponse(
            items=[ItemRead.model_validate(i) for i in items],
            total=total,
            skip=skip,
            limit=limit,
        )

    # ── mutations ─────────────────────────────────────────────────────────────

    async def create_item(self, payload: ItemCreate) -> ItemRead:
        data = payload.model_dump(exclude_none=False)
        item = await self._repo.create(data)
        log.info("Item created: {id}", id=item.id)
        return ItemRead.model_validate(item)

    async def update_item(self, item_id: uuid.UUID, payload: ItemUpdate) -> ItemRead:
        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise ValueError("No fields provided for update")
        item = await self._repo.update(item_id, data)
        log.info("Item updated: {id}", id=item_id)
        return ItemRead.model_validate(item)

    async def delete_item(self, item_id: uuid.UUID, *, hard: bool = False) -> None:
        if hard:
            await self._repo.hard_delete(item_id)
            log.info("Item hard-deleted: {id}", id=item_id)
        else:
            await self._repo.soft_delete(item_id)
            log.info("Item soft-deleted: {id}", id=item_id)

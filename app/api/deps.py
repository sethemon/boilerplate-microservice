"""
FastAPI dependency injection helpers.

Usage:
    from app.api.deps import DBSession, get_item_service

    @router.get("/items/{id}")
    async def get_item(item_id: uuid.UUID, db: DBSession):
        ...
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_dependency
from app.services.item_service import ItemService

# Re-usable annotated type for route signatures
DBSession = Annotated[AsyncSession, Depends(get_db_dependency)]


def get_item_service(db: DBSession) -> ItemService:
    return ItemService(db)


ItemServiceDep = Annotated[ItemService, Depends(get_item_service)]

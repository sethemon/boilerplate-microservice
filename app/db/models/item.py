"""
Example ORM model — replace / extend with your domain models.

Demonstrates:
  * UUID primary key (works across all supported databases)
  * created_at / updated_at auto-timestamps
  * soft-delete via is_deleted flag
  * JSON metadata column (supported by Postgres, MySQL 5.7+, SQLite 3.38+)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

from app.db.base import Base


# ── cross-DB UUID column ──────────────────────────────────────────────────────

class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses PostgreSQL's UUID natively; stores as CHAR(36) elsewhere.
    """

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value) if not isinstance(value, uuid.UUID) else value
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> uuid.UUID | None:
        return None if value is None else uuid.UUID(str(value))


# ─────────────────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Item(Base):
    """
    Generic 'Item' entity.  Demonstrates all common column types.

    DB operations example (in a repository / service):

        # CREATE
        item = Item(name="Widget", price=9.99)
        db.add(item)
        await db.flush()           # gets the auto-generated id

        # READ (single)
        result = await db.get(Item, item_id)

        # READ (filtered)
        stmt = select(Item).where(Item.is_deleted == False)
        rows  = (await db.execute(stmt)).scalars().all()

        # UPDATE
        item.name = "Updated Widget"
        await db.flush()

        # SOFT DELETE
        item.is_deleted = True
        await db.flush()

        # HARD DELETE
        await db.delete(item)
    """

    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Item id={self.id} name={self.name!r}>"

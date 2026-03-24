"""Pydantic v2 schemas for the Item resource."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, examples=["Widget"])
    description: str | None = Field(None, examples=["A great widget"])
    price: float = Field(0.0, ge=0.0, examples=[9.99])
    is_active: bool = Field(True)
    tags: dict[str, Any] | None = Field(None, examples=[{"color": "red"}])


class ItemCreate(ItemBase):
    """Payload for POST /items."""
    pass


class ItemUpdate(BaseModel):
    """Payload for PATCH /items/{id} — all fields optional."""
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    price: float | None = Field(None, ge=0.0)
    is_active: bool | None = None
    tags: dict[str, Any] | None = None


class ItemRead(ItemBase):
    """Response schema for a single Item."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class ItemListResponse(BaseModel):
    """Paginated list response."""
    items: list[ItemRead]
    total: int
    skip: int
    limit: int

"""
Items CRUD API — v1.

Routes
──────
  POST   /v1/items               create an item
  GET    /v1/items               list items (paginated)
  GET    /v1/items/{id}          get single item
  PATCH  /v1/items/{id}          partial update
  DELETE /v1/items/{id}          soft-delete (default) or hard-delete
  POST   /v1/items/{id}/publish  publish an item event to RabbitMQ (example)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.api.deps import ItemServiceDep
from app.logger import get_logger
from app.schemas.item import ItemCreate, ItemListResponse, ItemRead, ItemUpdate

log = get_logger(__name__)
router = APIRouter()


@router.post(
    "",
    response_model=ItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create item",
)
async def create_item(
    payload: ItemCreate,
    service: ItemServiceDep,
    request: Request,
) -> ItemRead:
    item = await service.create_item(payload)
    # Optionally publish event
    producer = getattr(request.app.state, "producer", None)
    if producer and producer.is_connected:
        await producer.publish(
            {"event": "item.created", "item_id": str(item.id)},
            routing_key="microservice.item.created",
        )
    return item


@router.get("", response_model=ItemListResponse, summary="List items")
async def list_items(
    service: ItemServiceDep,
    skip: Annotated[int, Query(ge=0, description="Records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=500, description="Max records")] = 100,
    name: Annotated[str | None, Query(description="Filter by name (partial match)")] = None,
) -> ItemListResponse:
    return await service.list_items(skip=skip, limit=limit, name_filter=name)


@router.get("/{item_id}", response_model=ItemRead, summary="Get item")
async def get_item(item_id: uuid.UUID, service: ItemServiceDep) -> ItemRead:
    try:
        return await service.get_item(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/{item_id}", response_model=ItemRead, summary="Update item")
async def update_item(
    item_id: uuid.UUID,
    payload: ItemUpdate,
    service: ItemServiceDep,
) -> ItemRead:
    try:
        return await service.update_item(item_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete item",
)
async def delete_item(
    item_id: uuid.UUID,
    service: ItemServiceDep,
    request: Request,
    hard: Annotated[bool, Query(description="Permanently delete the row")] = False,
) -> None:
    try:
        await service.delete_item(item_id, hard=hard)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    # Publish delete event
    producer = getattr(request.app.state, "producer", None)
    if producer and producer.is_connected:
        await producer.publish(
            {"event": "item.deleted", "item_id": str(item_id), "hard": hard},
            routing_key="microservice.item.deleted",
        )


@router.post(
    "/{item_id}/publish",
    summary="Publish item event to RabbitMQ",
    response_model=dict,
)
async def publish_item_event(
    item_id: uuid.UUID,
    service: ItemServiceDep,
    request: Request,
) -> dict:
    """Example: manually trigger a message-queue event for an item."""
    item = await service.get_item(item_id)  # raises 404 if not found
    producer = getattr(request.app.state, "producer", None)
    if producer is None or not producer.is_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RabbitMQ producer not available",
        )
    await producer.publish(
        {"event": "item.published", "item_id": str(item.id), "name": item.name},
        routing_key="microservice.item.published",
    )
    return {"published": True, "item_id": str(item.id)}

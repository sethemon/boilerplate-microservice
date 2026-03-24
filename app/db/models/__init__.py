"""
Import every model here so SQLAlchemy's metadata registry is fully populated
before create_all / alembic autogenerate runs.
"""
from app.db.models.item import Item  # noqa: F401

__all__ = ["Item"]

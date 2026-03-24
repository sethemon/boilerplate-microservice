"""SQLAlchemy declarative base shared by all models."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All ORM models inherit from this class."""
    pass

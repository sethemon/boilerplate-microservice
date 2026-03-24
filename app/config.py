"""
Centralised configuration.

Priority (highest → lowest):
  1. Environment variables
  2. .env file
  3. config/config.yaml
  4. hard-coded defaults below

Usage:
    from app.config import settings
    print(settings.app.name)
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── locate project root ───────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent


def _load_yaml() -> dict[str, Any]:
    """Load config/config.yaml, return empty dict if missing."""
    yaml_path = ROOT / "config" / "config.yaml"
    if yaml_path.exists():
        with yaml_path.open() as f:
            return yaml.safe_load(f) or {}
    return {}


_yaml: dict[str, Any] = _load_yaml()


def _y(*keys: str, default: Any = None) -> Any:
    """Drill into nested yaml dict: _y('database', 'url')."""
    node: Any = _yaml
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
    return node


# ─────────────────────────────────────────────────────────────────────────────

class AppSettings(BaseSettings):
    name: str = _y("app", "name", default="microservice")
    version: str = _y("app", "version", default="1.0.0")
    description: str = _y("app", "description", default="")
    environment: str = _y("app", "environment", default="development")
    host: str = _y("app", "host", default="0.0.0.0")
    port: int = _y("app", "port", default=8000)
    workers: int = _y("app", "workers", default=4)
    debug: bool = _y("app", "debug", default=False)
    secret_key: str = _y("app", "secret_key", default="change-me")
    allowed_origins: list[str] = _y("app", "allowed_origins", default=["*"])

    model_config = SettingsConfigDict(env_prefix="APP_", env_file=str(ROOT / ".env"), extra="ignore")


class DatabaseSettings(BaseSettings):
    # Override via DATABASE_URL env-var or set in config.yaml
    url: str = _y("database", "url", default="sqlite+aiosqlite:///./dev.db")
    pool_size: int = _y("database", "pool_size", default=10)
    max_overflow: int = _y("database", "max_overflow", default=20)
    pool_timeout: int = _y("database", "pool_timeout", default=30)
    pool_recycle: int = _y("database", "pool_recycle", default=3600)
    echo: bool = _y("database", "echo", default=False)

    @field_validator("url")
    @classmethod
    def _env_override(cls, v: str) -> str:
        return os.getenv("DATABASE_URL", v)

    model_config = SettingsConfigDict(env_prefix="DATABASE_", env_file=str(ROOT / ".env"), extra="ignore")

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return "postgresql" in self.url or "postgres" in self.url

    @property
    def is_mysql(self) -> bool:
        return "mysql" in self.url

    @property
    def is_mssql(self) -> bool:
        return "mssql" in self.url

    @property
    def is_oracle(self) -> bool:
        return "oracle" in self.url


class RabbitMQSettings(BaseSettings):
    url: str = _y("rabbitmq", "url", default="amqp://guest:guest@localhost:5672/")
    exchange_name: str = _y("rabbitmq", "exchange_name", default="microservice.exchange")
    exchange_type: str = _y("rabbitmq", "exchange_type", default="topic")
    queue_name: str = _y("rabbitmq", "queue_name", default="microservice.intake")
    routing_key: str = _y("rabbitmq", "routing_key", default="microservice.#")
    prefetch_count: int = _y("rabbitmq", "prefetch_count", default=10)
    reconnect_delay: int = _y("rabbitmq", "reconnect_delay", default=5)
    max_reconnect_attempts: int = _y("rabbitmq", "max_reconnect_attempts", default=10)
    durable: bool = _y("rabbitmq", "durable", default=True)

    @field_validator("url")
    @classmethod
    def _env_override(cls, v: str) -> str:
        return os.getenv("RABBITMQ_URL", v)

    model_config = SettingsConfigDict(env_prefix="RABBITMQ_", env_file=str(ROOT / ".env"), extra="ignore")


class LoggingSettings(BaseSettings):
    level: str = _y("logging", "level", default="INFO")
    file_path: str = _y("logging", "file_path", default="logs/app.log")
    rotation: str = _y("logging", "rotation", default="100 MB")
    retention: str = _y("logging", "retention", default="30 days")
    compression: str = _y("logging", "compression", default="gz")
    enqueue: bool = _y("logging", "enqueue", default=True)
    backtrace: bool = _y("logging", "backtrace", default=True)
    diagnose: bool = _y("logging", "diagnose", default=False)
    format: str = _y(
        "logging",
        "format",
        default="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {process} | {name}:{function}:{line} | {message}",
    )

    @field_validator("level")
    @classmethod
    def _env_override(cls, v: str) -> str:
        return os.getenv("LOG_LEVEL", v).upper()

    model_config = SettingsConfigDict(env_prefix="LOG_", env_file=str(ROOT / ".env"), extra="ignore")


class MetricsSettings(BaseSettings):
    enabled: bool = _y("metrics", "enabled", default=True)
    path: str = _y("metrics", "path", default="/metrics")

    model_config = SettingsConfigDict(env_prefix="METRICS_", env_file=str(ROOT / ".env"), extra="ignore")


class Settings:
    """Aggregate settings object — import this everywhere."""

    def __init__(self) -> None:
        self.app = AppSettings()
        self.database = DatabaseSettings()
        self.rabbitmq = RabbitMQSettings()
        self.logging = LoggingSettings()
        self.metrics = MetricsSettings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()

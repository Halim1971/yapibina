from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, ClassVar


def _environment_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _environment_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


class BaseConfig:
    APP_ENV = os.getenv("APP_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://localhost/yapibina",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SERVER_NAME = os.getenv("SERVER_NAME") or None
    SESSION_COOKIE_SECURE = _environment_bool("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_HTTPONLY = _environment_bool("SESSION_COOKIE_HTTPONLY", True)
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    MAX_CONTENT_LENGTH = _environment_int("MAX_CONTENT_LENGTH", 10_485_760)
    DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "Europe/Istanbul")
    DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "TRY")
    PLATFORM_HOSTNAME = os.getenv("PLATFORM_HOSTNAME", "platform.yapibina.com")
    BASE_TENANT_DOMAIN = os.getenv("BASE_TENANT_DOMAIN", "yapibina.com")

    WEAK_SECRET_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "",
            "change-me",
            "dev-only-change-me",
            "secret",
            "your-secret-key",
        }
    )

    @classmethod
    def validate(cls, config: Mapping[str, Any]) -> None:
        del config


class DevelopmentConfig(BaseConfig):
    APP_ENV = "development"
    DEBUG = True
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///yapibina-development.db",
    )


class TestingConfig(BaseConfig):
    APP_ENV = "testing"
    TESTING = True
    SECRET_KEY = "testing-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite+pysqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SERVER_NAME = None


class ProductionConfig(BaseConfig):
    APP_ENV = "production"
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True

    @classmethod
    def validate(cls, config: Mapping[str, Any]) -> None:
        secret_key = config.get("SECRET_KEY")
        if not isinstance(secret_key, str) or secret_key in cls.WEAK_SECRET_KEYS:
            raise RuntimeError(
                "Production requires a strong, non-default SECRET_KEY."
            )
        if len(secret_key) < 32:
            raise RuntimeError("Production SECRET_KEY must be at least 32 characters.")

        database_url = str(config.get("SQLALCHEMY_DATABASE_URI", ""))
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise RuntimeError("Production DATABASE_URL must use PostgreSQL.")

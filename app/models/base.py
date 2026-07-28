from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column

SLUG_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9]+")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("A valid email address is required.")
    return normalized


def normalize_slug(value: str) -> str:
    transliterated = value.strip().casefold()
    for source, target in (
        ("ı", "i"),
        ("ş", "s"),
        ("ğ", "g"),
        ("ü", "u"),
        ("ö", "o"),
        ("ç", "c"),
    ):
        transliterated = transliterated.replace(source, target)
    ascii_value = (
        unicodedata.normalize("NFKD", transliterated)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    normalized = SLUG_SEPARATOR_PATTERN.sub("-", ascii_value).strip("-")
    if not normalized:
        raise ValueError("A URL-safe organization slug is required.")
    return normalized


def normalize_hostname_value(value: str) -> str:
    candidate = value.strip().lower().rstrip(".")
    if not candidate or "://" in candidate or "/" in candidate:
        raise ValueError("Hostname must not include a scheme, port or path.")
    parsed = urlsplit(f"//{candidate}")
    if parsed.port is not None or parsed.hostname != candidate:
        raise ValueError("Hostname must not include a scheme, port or path.")
    try:
        normalized = candidate.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ValueError("Hostname is invalid.") from error
    if len(normalized) > 253 or any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not re.fullmatch(r"[a-z0-9-]+", label)
        for label in normalized.split(".")
    ):
        raise ValueError("Hostname is invalid.")
    return normalized


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

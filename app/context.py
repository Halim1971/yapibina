from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Final
from zoneinfo import ZoneInfo

from flask import Flask, g

from app.extensions import db
from app.services.organization_branding import get_effective_branding

DEFAULT_THEME: Final[dict[str, str]] = {
    "primary": "#0f3f3f",
    "secondary": "#d4d9d5",
    "surface": "#f4f4f4",
    "white": "#ffffff",
}


def format_try(value: Decimal) -> str:
    formatted = f"{value:,.2f}"
    return (
        formatted.replace(",", "\u0000")
        .replace(".", ",")
        .replace("\u0000", ".")
    )


def register_context_processors(app: Flask) -> None:
    @app.template_filter("datetime_tr")
    def datetime_tr(value: datetime) -> str:
        return value.astimezone(
            ZoneInfo(app.config["DEFAULT_TIMEZONE"])
        ).strftime("%d.%m.%Y %H:%M")

    @app.context_processor
    def default_theme() -> dict[str, object]:
        tenant = getattr(g, "tenant", None)
        branding = get_effective_branding(
            db.session,
            organization_id=(
                uuid.UUID(tenant.organization_id) if tenant is not None else None
            ),
        )
        theme = {
            "primary": branding.primary_color,
            "secondary": branding.secondary_color,
            "surface": branding.background_color,
            "white": branding.surface_color,
        }
        return {"branding": branding, "theme": theme, "format_try": format_try}

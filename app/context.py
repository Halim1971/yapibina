from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Final

from flask import Flask, g

from app.extensions import db
from app.models import OrganizationBranding

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
    @app.context_processor
    def default_theme() -> dict[str, object]:
        theme = DEFAULT_THEME.copy()
        tenant = getattr(g, "tenant", None)
        if tenant is not None:
            branding = db.session.scalar(
                db.select(OrganizationBranding).where(
                    OrganizationBranding.organization_id == uuid.UUID(tenant.organization_id)
                )
            )
            if branding is not None:
                theme.update(
                    {
                        key: value
                        for key, value in {
                            "primary": branding.primary_color,
                            "secondary": branding.secondary_color,
                            "surface": branding.surface_color,
                        }.items()
                        if value
                    }
                )
        return {"theme": theme, "format_try": format_try}

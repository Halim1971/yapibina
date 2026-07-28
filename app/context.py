from __future__ import annotations

from typing import Final

from flask import Flask

DEFAULT_THEME: Final[dict[str, str]] = {
    "primary": "#0f3f3f",
    "secondary": "#d4d9d5",
    "surface": "#f4f4f4",
    "white": "#ffffff",
}


def register_context_processors(app: Flask) -> None:
    @app.context_processor
    def default_theme() -> dict[str, dict[str, str]]:
        # A later branding service may safely override these values per tenant.
        return {"theme": DEFAULT_THEME.copy()}

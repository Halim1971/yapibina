import pytest
from flask import Flask

from app import create_app
from config.settings import ProductionConfig


class MissingTenantLookup:
    def resolve(self, hostname: str) -> None:
        del hostname
        return None


def test_unknown_production_hostname_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "x" * 48)
    app = create_app("production")
    app.extensions["tenant_hostname_lookup"] = MissingTenantLookup()

    response = app.test_client().get(
        "/missing",
        headers={"Host": "unknown.example"},
    )

    assert response.status_code == 421


def test_development_localhost_is_allowed() -> None:
    app = create_app("development")

    response = app.test_client().get(
        "/missing",
        headers={"Host": "localhost"},
    )

    assert response.status_code == 404


def test_theme_defaults_are_available_in_template_context(app: Flask) -> None:
    with app.test_request_context("/"):
        context: dict[str, object] = {}
        app.update_template_context(context)

    assert context["theme"] == {
        "primary": "#0f3f3f",
        "secondary": "#d4d9d5",
        "surface": "#f4f4f4",
        "white": "#ffffff",
    }

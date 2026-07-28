import pytest

from app import create_app
from config.settings import ProductionConfig, TestingConfig


def test_testing_config_does_not_require_production_secret() -> None:
    app = create_app("testing")

    assert app.config["TESTING"] is True
    assert app.config["SECRET_KEY"] == TestingConfig.SECRET_KEY


def test_production_security_settings_are_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "x" * 48)
    app = create_app("production")

    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["REMEMBER_COOKIE_SECURE"] is True
    assert app.config["WTF_CSRF_ENABLED"] is True


@pytest.mark.parametrize("weak_secret", [None, "", "change-me", "short"])
def test_production_rejects_missing_or_weak_secret(
    monkeypatch: pytest.MonkeyPatch,
    weak_secret: str | None,
) -> None:
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", weak_secret)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")

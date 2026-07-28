from flask import Flask

from app import create_app


def test_create_app_with_testing_config() -> None:
    app = create_app("testing")

    assert isinstance(app, Flask)
    assert app.config["APP_ENV"] == "testing"
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite+pysqlite:///:memory:"
    assert "sqlalchemy" in app.extensions
    assert "migrate" in app.extensions
    assert "tenant_hostname_lookup" in app.extensions

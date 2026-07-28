from __future__ import annotations

import os

from flask import Flask

from app import models as models
from app.blueprints import register_blueprints
from app.context import register_context_processors
from app.errors import register_error_handlers
from app.extensions import csrf, db, limiter, login_manager, migrate
from app.tenant.resolver import register_tenant_resolution
from config import get_config


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure a Yapıbina Flask application."""
    selected_config = config_name or os.getenv("APP_ENV") or "development"
    config_class = get_config(selected_config)

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    config_class.validate(app.config)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Bu sayfayı görüntülemek için giriş yapmalısınız."
    login_manager.login_message_category = "warning"
    csrf.init_app(app)
    limiter.init_app(app)

    register_blueprints(app)
    register_error_handlers(app)
    register_context_processors(app)
    register_tenant_resolution(app)

    return app


__all__ = ["create_app", "models"]

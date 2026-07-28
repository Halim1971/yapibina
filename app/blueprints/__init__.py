from flask import Flask

from app.blueprints.auth import auth_blueprint
from app.blueprints.organization import organization_blueprint
from app.blueprints.platform import platform_blueprint
from app.blueprints.public import public_blueprint
from app.blueprints.resident import resident_blueprint


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(public_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(platform_blueprint)
    app.register_blueprint(organization_blueprint)
    app.register_blueprint(resident_blueprint)

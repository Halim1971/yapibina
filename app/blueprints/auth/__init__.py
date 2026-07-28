from flask import Blueprint

auth_blueprint = Blueprint("auth", __name__, url_prefix="/auth")

from app.blueprints.auth import routes as routes  # noqa: E402,F401

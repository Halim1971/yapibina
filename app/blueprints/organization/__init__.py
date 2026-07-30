# ruff: noqa: E402

from flask import Blueprint

organization_blueprint = Blueprint("organization", __name__, url_prefix="/organization")

from app.blueprints.organization import announcement_routes as announcement_routes  # noqa: F401
from app.blueprints.organization import import_routes as import_routes  # noqa: F401
from app.blueprints.organization import routes as routes  # noqa: F401

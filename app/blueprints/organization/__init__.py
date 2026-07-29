from flask import Blueprint

organization_blueprint = Blueprint("organization", __name__, url_prefix="/organization")

from app.blueprints.organization import import_routes as import_routes  # noqa: E402,F401
from app.blueprints.organization import routes as routes  # noqa: E402,F401

from flask import Blueprint

platform_blueprint = Blueprint("platform", __name__, url_prefix="/platform")

from app.blueprints.platform import routes as routes  # noqa: E402,F401

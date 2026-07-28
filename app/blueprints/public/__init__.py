from flask import Blueprint

public_blueprint = Blueprint("public", __name__)

from app.blueprints.public import routes as routes  # noqa: E402,F401

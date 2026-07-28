from flask import Blueprint

resident_blueprint = Blueprint("resident", __name__)

from app.blueprints.resident import routes as routes  # noqa: E402,F401

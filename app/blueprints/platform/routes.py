from flask import Response, jsonify

from app.auth.decorators import platform_admin_required
from app.blueprints.platform import platform_blueprint


@platform_blueprint.get("/")
@platform_admin_required
def index() -> Response:
    return jsonify(area="platform")

from flask import Response, jsonify

from app.auth.decorators import organization_member_required
from app.blueprints.organization import organization_blueprint


@organization_blueprint.get("/")
@organization_member_required
def index() -> Response:
    return jsonify(area="organization")

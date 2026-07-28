from flask import Response, jsonify

from app.auth.decorators import resident_required
from app.blueprints.resident import resident_blueprint


@resident_blueprint.get("/resident/")
@resident_required
def index() -> Response:
    return jsonify(area="resident")

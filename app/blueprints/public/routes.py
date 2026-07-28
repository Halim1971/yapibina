from flask import Response, jsonify

from app.blueprints.public import public_blueprint


@public_blueprint.get("/health")
def health() -> tuple[Response, int]:
    return jsonify(status="ok", service="yapibina"), 200

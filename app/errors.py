from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def _wants_json_response() -> bool:
    if request.path == "/health":
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and (
        request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]
    )


def _error_response(status_code: int, message: str) -> tuple[Any, int]:
    if _wants_json_response():
        return jsonify(error={"code": status_code, "message": message}), status_code
    return render_template(f"errors/{status_code}.html", status_code=status_code), status_code


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_: HTTPException) -> tuple[Any, int]:
        return _error_response(HTTPStatus.NOT_FOUND, "Sayfa bulunamadı.")

    @app.errorhandler(421)
    def misdirected_request(_: HTTPException) -> tuple[Any, int]:
        return _error_response(
            HTTPStatus.MISDIRECTED_REQUEST,
            "Bu alan adı Yapıbina üzerinde tanımlı değil.",
        )

    @app.errorhandler(500)
    def internal_server_error(error: HTTPException) -> tuple[Any, int]:
        logger.error("Unhandled application error", exc_info=error)
        return _error_response(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "Beklenmeyen bir hata oluştu.",
        )

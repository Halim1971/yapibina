from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
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
    @app.errorhandler(CSRFError)
    def csrf_error(_: CSRFError) -> tuple[Any, int]:
        return _error_response(
            HTTPStatus.BAD_REQUEST,
            "Güvenlik doğrulaması başarısız oldu. Lütfen yeniden deneyin.",
        )

    @app.errorhandler(400)
    def bad_request(_: HTTPException) -> tuple[Any, int]:
        return _error_response(HTTPStatus.BAD_REQUEST, "Geçersiz istek.")

    @app.errorhandler(403)
    def forbidden(_: HTTPException) -> tuple[Any, int]:
        return _error_response(HTTPStatus.FORBIDDEN, "Bu işlem için yetkiniz yok.")

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

    @app.errorhandler(429)
    def too_many_requests(_: HTTPException) -> tuple[Any, int]:
        return _error_response(
            HTTPStatus.TOO_MANY_REQUESTS,
            "Çok fazla giriş denemesi yapıldı. Lütfen daha sonra yeniden deneyin.",
        )

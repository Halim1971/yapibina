from __future__ import annotations

from flask import Flask


def register_import_commands(app: Flask) -> None:
    from app.imports.cli import register_import_commands as register

    register(app)


__all__ = ["register_import_commands"]

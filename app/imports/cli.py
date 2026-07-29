from __future__ import annotations

import uuid
from pathlib import Path

import click
from flask import Flask

from app.extensions import db
from app.imports.constants import SOURCE_SYSTEM_STANDARD_EXCEL
from app.imports.exceptions import ImporterError
from app.imports.reader import read_standard_package
from app.imports.service import import_standard_package
from app.services import ServiceValidationError


def register_import_commands(app: Flask) -> None:
    @app.cli.command("import-standard-data")
    @click.option(
        "--organization-id",
        required=True,
        type=click.UUID,
        help="Hedef organization UUID değeri.",
    )
    @click.option(
        "--path",
        "package_path",
        required=True,
        type=click.Path(path_type=Path, exists=True, file_okay=False),
        help="Standart veri paketi dizini.",
    )
    @click.option(
        "--source-system",
        default=SOURCE_SYSTEM_STANDARD_EXCEL,
        show_default=True,
    )
    @click.option("--created-by-user-id", type=click.UUID)
    @click.option("--dry-run", is_flag=True, help="Kalıcı değişiklik yapmadan planla.")
    def import_standard_data(
        organization_id: uuid.UUID,
        package_path: Path,
        source_system: str,
        created_by_user_id: uuid.UUID | None,
        dry_run: bool,
    ) -> None:
        try:
            package = read_standard_package(package_path)
            result = import_standard_package(
                db.session,
                organization_id=organization_id,
                package=package,
                source_system=source_system,
                created_by_user_id=created_by_user_id,
                dry_run=dry_run,
            )
        except (ImporterError, ServiceValidationError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"organization={organization_id}")
        click.echo(f"package={package.dataset_name}")
        click.echo(f"fingerprint={result.fingerprint}")
        click.echo(f"status={result.status}")
        click.echo(f"inserted={result.inserted}")
        click.echo(f"updated={result.updated}")
        click.echo(f"skipped={result.skipped}")
        click.echo(f"deferred={result.deferred}")
        click.echo("failed=0")

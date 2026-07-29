from __future__ import annotations

import uuid
from typing import Any

from flask import (
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy import select

from app.auth.decorators import organization_admin_required
from app.blueprints.organization import organization_blueprint
from app.blueprints.organization.forms import ImportConfirmForm, ImportPackageForm
from app.extensions import db
from app.imports.constants import SOURCE_SYSTEM_STANDARD_EXCEL
from app.imports.exceptions import (
    CriticalFinancialChangeError,
    ImporterError,
    PackageValidationError,
)
from app.imports.models import ImportRun
from app.imports.service import import_standard_package
from app.imports.staging import (
    cleanup_staged_package,
    load_staged_package,
    stage_package,
)
from app.models import User
from app.services import ServiceValidationError

PREVIEW_SESSION_KEY = "standard_import_preview"


def _organization_id() -> uuid.UUID:
    return uuid.UUID(g.tenant.organization_id)


def _actor_names(runs: list[ImportRun]) -> dict[uuid.UUID, str]:
    user_ids = {
        run.created_by_user_id
        for run in runs
        if run.created_by_user_id is not None
    }
    if not user_ids:
        return {}
    users = db.session.scalars(select(User).where(User.id.in_(user_ids))).all()
    return {
        user.id: f"{user.first_name} {user.last_name}".strip() or user.email
        for user in users
    }


def _discard_preview() -> None:
    preview = session.pop(PREVIEW_SESSION_KEY, None)
    if not isinstance(preview, dict):
        return
    if preview.get("organization_id") != str(_organization_id()):
        return
    token = preview.get("token")
    if not isinstance(token, str):
        return
    try:
        cleanup_staged_package(
            instance_path=current_app.instance_path,
            organization_id=_organization_id(),
            token=token,
        )
    except PackageValidationError:
        current_app.logger.warning("Invalid staged import token was discarded.")


@organization_blueprint.get("/imports")
@organization_admin_required
def imports() -> str:
    page = max(request.args.get("page", 1, type=int), 1)
    statement = (
        select(ImportRun)
        .where(ImportRun.organization_id == _organization_id())
        .order_by(ImportRun.started_at.desc(), ImportRun.id.desc())
    )
    pagination = db.paginate(
        statement,
        page=page,
        per_page=current_app.config["MANAGEMENT_PAGE_SIZE"],
        error_out=False,
    )
    return render_template(
        "organization/imports/index.html",
        pagination=pagination,
        actor_names=_actor_names(list(pagination.items)),
    )


@organization_blueprint.route("/imports/new", methods=["GET", "POST"])
@organization_admin_required
def import_new() -> Any:
    form = ImportPackageForm()
    if request.method == "GET":
        _discard_preview()
    if not form.validate_on_submit():
        return render_template("organization/imports/new.html", form=form)

    uploaded = form.package.data
    _discard_preview()
    staged = None
    try:
        staged = stage_package(
            uploaded,
            instance_path=current_app.instance_path,
            organization_id=_organization_id(),
            max_archive_bytes=current_app.config["IMPORT_PACKAGE_MAX_BYTES"],
            max_extracted_bytes=current_app.config["IMPORT_EXTRACTED_MAX_BYTES"],
        )
        result = import_standard_package(
            db.session,
            organization_id=_organization_id(),
            package=staged.package,
            source_system=SOURCE_SYSTEM_STANDARD_EXCEL,
            created_by_user_id=current_user.id,
            dry_run=True,
        )
    except CriticalFinancialChangeError as error:
        if staged is not None:
            cleanup_staged_package(
                instance_path=current_app.instance_path,
                organization_id=_organization_id(),
                token=staged.token,
            )
        flash("Finansal kayıt çakışması tespit edildi.", "error")
        current_app.logger.warning("Import dry-run financial conflict: %s", error)
        return render_template("organization/imports/new.html", form=form)
    except (ImporterError, ServiceValidationError) as error:
        if staged is not None:
            cleanup_staged_package(
                instance_path=current_app.instance_path,
                organization_id=_organization_id(),
                token=staged.token,
            )
        flash(str(error), "error")
        return render_template("organization/imports/new.html", form=form)

    session[PREVIEW_SESSION_KEY] = {
        "organization_id": str(_organization_id()),
        "token": staged.token,
        "fingerprint": staged.package.fingerprint,
        "source_system": SOURCE_SYSTEM_STANDARD_EXCEL,
    }
    confirm_form = ImportConfirmForm(
        staging_token=staged.token,
        fingerprint=staged.package.fingerprint,
    )
    return render_template(
        "organization/imports/preview.html",
        package=staged.package,
        result=result,
        confirm_form=confirm_form,
    )


@organization_blueprint.post("/imports/cancel")
@organization_admin_required
def import_cancel() -> Any:
    _discard_preview()
    flash("Veri paketi silindi; içe aktarma başlatılmadı.", "info")
    return redirect(url_for("organization.imports"))


@organization_blueprint.post("/imports/confirm")
@organization_admin_required
def import_confirm() -> Any:
    form = ImportConfirmForm()
    preview = session.get(PREVIEW_SESSION_KEY)
    if not form.validate_on_submit() or not isinstance(preview, dict):
        abort(400)
    expected = {
        "organization_id": str(_organization_id()),
        "token": form.staging_token.data,
        "fingerprint": form.fingerprint.data,
        "source_system": SOURCE_SYSTEM_STANDARD_EXCEL,
    }
    if preview != expected:
        abort(400)

    session.pop(PREVIEW_SESSION_KEY, None)
    token = form.staging_token.data
    try:
        staged = load_staged_package(
            instance_path=current_app.instance_path,
            organization_id=_organization_id(),
            token=token,
        )
        if staged.package.fingerprint != form.fingerprint.data:
            raise PackageValidationError("Paket ön kontrolden sonra değişmiş.")
        result = import_standard_package(
            db.session,
            organization_id=_organization_id(),
            package=staged.package,
            source_system=SOURCE_SYSTEM_STANDARD_EXCEL,
            created_by_user_id=current_user.id,
        )
    except CriticalFinancialChangeError as error:
        current_app.logger.warning("Import financial conflict: %s", error)
        flash("Finansal kayıt çakışması tespit edildi.", "error")
        return redirect(url_for("organization.imports"))
    except (ImporterError, ServiceValidationError) as error:
        current_app.logger.warning("Import failed safely: %s", error)
        flash("İşlem başarısız oldu; hiçbir veri değiştirilmedi.", "error")
        return redirect(url_for("organization.imports"))
    finally:
        cleanup_staged_package(
            instance_path=current_app.instance_path,
            organization_id=_organization_id(),
            token=token,
        )

    if result.status == "already_imported":
        flash("Bu paket daha önce içe aktarılmış.", "info")
    else:
        flash("Veri paketi başarıyla içe aktarıldı.", "success")
    if result.run_id is None:
        return redirect(url_for("organization.imports"))
    return redirect(
        url_for(
            "organization.import_detail",
            import_run_id=result.run_id,
        )
    )


@organization_blueprint.get("/imports/<uuid:import_run_id>")
@organization_admin_required
def import_detail(import_run_id: uuid.UUID) -> str:
    run = db.session.scalar(
        select(ImportRun).where(
            ImportRun.id == import_run_id,
            ImportRun.organization_id == _organization_id(),
        )
    )
    if run is None:
        abort(404)
    actor = (
        db.session.get(User, run.created_by_user_id)
        if run.created_by_user_id is not None
        else None
    )
    return render_template(
        "organization/imports/detail.html",
        run=run,
        actor_name=(
            f"{actor.first_name} {actor.last_name}".strip() or actor.email
            if actor is not None
            else "Sistem"
        ),
    )

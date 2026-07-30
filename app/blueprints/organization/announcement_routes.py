from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from app.auth.decorators import organization_admin_required
from app.blueprints.organization import organization_blueprint
from app.blueprints.organization.forms import AnnouncementForm
from app.extensions import db
from app.models import Announcement, AnnouncementAudienceScope, Building
from app.models.base import utc_now
from app.services import EntityNotFoundError, ServiceValidationError
from app.services.organization_announcements import (
    archive_announcement,
    create_announcement,
    get_organization_announcement,
    list_organization_announcements,
    publish_announcement,
    update_draft_announcement,
)


def _organization_id() -> uuid.UUID:
    return uuid.UUID(g.tenant.organization_id)


def _safe_int(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


def _aware_local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    timezone_name = current_app.config["DEFAULT_TIMEZONE"]
    return value.replace(tzinfo=ZoneInfo(timezone_name))


def _publish_at(form: AnnouncementForm) -> datetime | None:
    if form.publication_mode.data == "draft":
        return None
    if form.publication_mode.data == "now":
        return utc_now()
    if form.published_at.data is None:
        form.published_at.errors.append("İleri tarihli yayın zamanı zorunludur.")
        return None
    scheduled = _aware_local(form.published_at.data)
    return utc_now() if scheduled is not None and scheduled <= utc_now() else scheduled


def _building_choices() -> list[tuple[str, str]]:
    return [
        (str(building.id), building.name)
        for building in db.session.scalars(
            select(Building)
            .where(
                Building.organization_id == _organization_id(),
                Building.is_active.is_(True),
            )
            .order_by(Building.name, Building.id)
        )
    ]


def _building_ids(form: AnnouncementForm) -> tuple[uuid.UUID, ...]:
    return tuple(uuid.UUID(value) for value in form.building_ids.data)


def _save_form_error(form: AnnouncementForm, action: Any) -> bool:
    try:
        action()
        db.session.commit()
    except ServiceValidationError as error:
        db.session.rollback()
        form.form_errors.append(str(error))
        return False
    return True


@organization_blueprint.get("/announcements")
@organization_admin_required
def announcements() -> str:
    building_choices = _building_choices()
    selected_building_id: uuid.UUID | None = None
    raw_building_id = request.args.get("building_id", "").strip()
    if raw_building_id:
        try:
            selected_building_id = uuid.UUID(raw_building_id)
        except ValueError:
            abort(404)
        if str(selected_building_id) not in {
            building_id for building_id, _ in building_choices
        }:
            abort(404)
    listing = list_organization_announcements(
        db.session,
        organization_id=_organization_id(),
        status_filter=request.args.get("status", ""),
        building_id=selected_building_id,
        sort=request.args.get("sort", "created_at"),
        direction=request.args.get("direction", "desc"),
        page=_safe_int("page", 1),
        per_page=_safe_int(
            "per_page", current_app.config["MANAGEMENT_PAGE_SIZE"]
        ),
    )
    return render_template(
        "organization/announcements/index.html",
        listing=listing,
        building_choices=building_choices,
    )


@organization_blueprint.get("/announcements/new")
@organization_admin_required
def announcement_new() -> str:
    form = AnnouncementForm()
    form.set_building_choices(_building_choices())
    return render_template(
        "organization/announcements/form.html",
        form=form,
        title="Yeni Duyuru",
        submit_url=url_for("organization.announcement_create"),
    )


@organization_blueprint.post("/announcements")
@organization_admin_required
def announcement_create() -> Any:
    form = AnnouncementForm()
    form.set_building_choices(_building_choices())
    if form.validate_on_submit():
        publish_at = _publish_at(form)
        if form.publication_mode.data != "future" or publish_at is not None:
            created: list[Announcement] = []
            if _save_form_error(
                form,
                lambda: created.append(
                    create_announcement(
                        db.session,
                        organization_id=_organization_id(),
                        created_by_user_id=current_user.id,
                        title=form.title.data,
                        body=form.body.data,
                        audience_scope=AnnouncementAudienceScope(
                            form.audience_scope.data
                        ),
                        building_ids=_building_ids(form),
                        publish_at=publish_at,
                        expires_at=_aware_local(form.expires_at.data),
                    )
                ),
            ):
                announcement = created[0]
                flash("Duyuru kaydedildi.", "success")
                return redirect(
                    url_for(
                        "organization.announcement_detail",
                        announcement_id=announcement.id,
                    )
                )
    return render_template(
        "organization/announcements/form.html",
        form=form,
        title="Yeni Duyuru",
        submit_url=url_for("organization.announcement_create"),
    ), 400


@organization_blueprint.get("/announcements/<uuid:announcement_id>")
@organization_admin_required
def announcement_detail(announcement_id: uuid.UUID) -> str:
    try:
        detail = get_organization_announcement(
            db.session,
            organization_id=_organization_id(),
            announcement_id=announcement_id,
        )
    except EntityNotFoundError:
        abort(404)
    return render_template(
        "organization/announcements/detail.html", announcement=detail
    )


@organization_blueprint.get("/announcements/<uuid:announcement_id>/edit")
@organization_admin_required
def announcement_edit(announcement_id: uuid.UUID) -> str:
    try:
        detail = get_organization_announcement(
            db.session,
            organization_id=_organization_id(),
            announcement_id=announcement_id,
        )
    except EntityNotFoundError:
        abort(404)
    if not detail.can_edit:
        abort(400)
    publication_mode = (
        "future" if detail.published_at is not None else "draft"
    )
    form = AnnouncementForm(
        data={
            "title": detail.title,
            "body": detail.body,
            "audience_scope": detail.audience_scope.value,
            "building_ids": [str(item[0]) for item in detail.target_buildings],
            "publication_mode": publication_mode,
            "published_at": detail.published_at,
            "expires_at": detail.expires_at,
        }
    )
    form.set_building_choices(_building_choices())
    return render_template(
        "organization/announcements/form.html",
        form=form,
        title="Duyuruyu Düzenle",
        submit_url=url_for(
            "organization.announcement_update", announcement_id=announcement_id
        ),
    )


@organization_blueprint.post("/announcements/<uuid:announcement_id>/edit")
@organization_admin_required
def announcement_update(announcement_id: uuid.UUID) -> Any:
    form = AnnouncementForm()
    form.set_building_choices(_building_choices())
    if form.validate_on_submit():
        publish_at = _publish_at(form)
        if (
            form.publication_mode.data != "future" or publish_at is not None
        ) and _save_form_error(
                form,
                lambda: update_draft_announcement(
                    db.session,
                    organization_id=_organization_id(),
                    announcement_id=announcement_id,
                    title=form.title.data,
                    body=form.body.data,
                    audience_scope=AnnouncementAudienceScope(
                        form.audience_scope.data
                    ),
                    building_ids=_building_ids(form),
                    publish_at=publish_at,
                    expires_at=_aware_local(form.expires_at.data),
                ),
            ):
            flash("Duyuru güncellendi.", "success")
            return redirect(
                url_for(
                    "organization.announcement_detail",
                    announcement_id=announcement_id,
                )
            )
    return render_template(
        "organization/announcements/form.html",
        form=form,
        title="Duyuruyu Düzenle",
        submit_url=url_for(
            "organization.announcement_update", announcement_id=announcement_id
        ),
    ), 400


def _transition(announcement_id: uuid.UUID, *, archive: bool) -> Any:
    try:
        if archive:
            archive_announcement(
                db.session,
                organization_id=_organization_id(),
                announcement_id=announcement_id,
            )
            message = "Duyuru arşivlendi."
        else:
            publish_announcement(
                db.session,
                organization_id=_organization_id(),
                announcement_id=announcement_id,
            )
            message = "Duyuru yayınlandı."
        db.session.commit()
    except EntityNotFoundError:
        db.session.rollback()
        abort(404)
    except ServiceValidationError as error:
        db.session.rollback()
        flash(str(error), "error")
    else:
        flash(message, "success")
    return redirect(
        url_for(
            "organization.announcement_detail", announcement_id=announcement_id
        )
    )


@organization_blueprint.post("/announcements/<uuid:announcement_id>/publish")
@organization_admin_required
def announcement_publish(announcement_id: uuid.UUID) -> Any:
    return _transition(announcement_id, archive=False)


@organization_blueprint.post("/announcements/<uuid:announcement_id>/archive")
@organization_admin_required
def announcement_archive(announcement_id: uuid.UUID) -> Any:
    return _transition(announcement_id, archive=True)

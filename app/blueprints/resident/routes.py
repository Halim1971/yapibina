from __future__ import annotations

import uuid
from typing import Any

from flask import abort, g, redirect, render_template, request, url_for
from flask_login import current_user

from app.auth.decorators import resident_required
from app.blueprints.resident import resident_blueprint
from app.extensions import db
from app.services import EntityNotFoundError
from app.services.resident_announcements import (
    get_resident_announcement,
    list_resident_announcements,
)
from app.services.resident_finances import (
    format_try,
    get_resident_account_statement,
    get_resident_dashboard,
    get_resident_payments,
    resolve_resident_apartment,
)
from app.services.resident_notifications import (
    list_resident_notifications,
    mark_announcement_read,
)


def _organization_id() -> uuid.UUID:
    return uuid.UUID(g.tenant.organization_id)


def _requested_apartment_id() -> uuid.UUID | None:
    raw_value = request.args.get("apartment_id")
    if not raw_value:
        return None
    try:
        return uuid.UUID(raw_value)
    except ValueError:
        abort(404)


def _page() -> int:
    try:
        return max(int(request.args.get("page", "1")), 1)
    except ValueError:
        return 1


@resident_blueprint.get("/resident/")
@resident_required
def index() -> Any:
    try:
        dashboard = get_resident_dashboard(
            db.session,
            organization_id=_organization_id(),
            user_id=current_user.id,
            apartment_id=_requested_apartment_id(),
        )
    except EntityNotFoundError:
        abort(404)
    return render_template(
        "resident/dashboard.html",
        dashboard=dashboard,
        format_try=format_try,
    )


@resident_blueprint.get("/resident/account")
@resident_required
def account() -> Any:
    try:
        selected, apartments = resolve_resident_apartment(
            db.session,
            organization_id=_organization_id(),
            user_id=current_user.id,
            apartment_id=_requested_apartment_id(),
        )
        statement = (
            get_resident_account_statement(
                db.session,
                organization_id=_organization_id(),
                user_id=current_user.id,
                apartment_id=selected.id,
                page=_page(),
            )
            if selected
            else None
        )
    except EntityNotFoundError:
        abort(404)
    return render_template(
        "resident/account.html",
        selected=selected,
        apartments=apartments,
        statement=statement,
        format_try=format_try,
    )


@resident_blueprint.get("/resident/payments")
@resident_required
def payments() -> Any:
    try:
        selected, apartments = resolve_resident_apartment(
            db.session,
            organization_id=_organization_id(),
            user_id=current_user.id,
            apartment_id=_requested_apartment_id(),
        )
        payment_page = (
            get_resident_payments(
                db.session,
                organization_id=_organization_id(),
                user_id=current_user.id,
                apartment_id=selected.id,
                page=_page(),
            )
            if selected
            else None
        )
    except EntityNotFoundError:
        abort(404)
    return render_template(
        "resident/payments.html",
        selected=selected,
        apartments=apartments,
        payment_page=payment_page,
        format_try=format_try,
    )


@resident_blueprint.get("/resident/transactions")
@resident_required
def transactions() -> Any:
    return redirect(
        url_for(
            "resident.account",
            apartment_id=request.args.get("apartment_id"),
            page=request.args.get("page"),
        )
    )


@resident_blueprint.get("/resident/announcements")
@resident_required
def announcements() -> str:
    listing = list_resident_announcements(
        db.session,
        organization_id=_organization_id(),
        user_id=current_user.id,
        page=_page(),
        per_page=request.args.get("per_page", 20, type=int) or 20,
    )
    return render_template("resident/announcements/index.html", listing=listing)


@resident_blueprint.get("/resident/announcements/<uuid:announcement_id>")
@resident_required
def announcement_detail(announcement_id: uuid.UUID) -> str:
    try:
        announcement = get_resident_announcement(
            db.session,
            organization_id=_organization_id(),
            user_id=current_user.id,
            announcement_id=announcement_id,
        )
        mark_announcement_read(
            db.session,
            organization_id=_organization_id(),
            user_id=current_user.id,
            announcement_id=announcement_id,
        )
        db.session.commit()
    except EntityNotFoundError:
        db.session.rollback()
        abort(404)
    return render_template("resident/announcements/detail.html", announcement=announcement)


@resident_blueprint.get("/resident/notifications")
@resident_required
def notifications() -> str:
    listing = list_resident_notifications(
        db.session,
        organization_id=_organization_id(),
        user_id=current_user.id,
        state_filter=request.args.get("state", "all"),
        page=_page(),
        per_page=request.args.get("per_page", 20, type=int) or 20,
    )
    return render_template("resident/notifications/index.html", listing=listing)


@resident_blueprint.post("/resident/notifications/<uuid:announcement_id>/read")
@resident_required
def notification_mark_read(announcement_id: uuid.UUID) -> Any:
    try:
        mark_announcement_read(
            db.session,
            organization_id=_organization_id(),
            user_id=current_user.id,
            announcement_id=announcement_id,
        )
        db.session.commit()
    except EntityNotFoundError:
        db.session.rollback()
        abort(404)
    return redirect(url_for("resident.notifications"))

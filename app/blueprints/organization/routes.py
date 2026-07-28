from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from sqlalchemy import or_, select

from app.auth.decorators import organization_admin_required
from app.blueprints.organization import organization_blueprint
from app.blueprints.organization.forms import ApartmentForm, BuildingForm, MembershipForm, UserForm
from app.extensions import db
from app.models import (
    Apartment,
    ApartmentMembershipRole,
    Building,
    BuildingMembershipRole,
    OrganizationMembership,
    OrganizationMembershipRole,
    User,
)
from app.services import ServiceValidationError
from app.services.organization_management import (
    create_apartment,
    create_building,
    update_apartment,
    update_building,
)
from app.services.tenancy import require_apartment, require_building
from app.services.user_management import (
    assign_apartment_membership,
    assign_building_membership,
    assign_organization_membership,
    deactivate_membership,
    resolve_or_create_user,
)


def _organization_id() -> uuid.UUID:
    return uuid.UUID(g.tenant.organization_id)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _commit_or_form_error(form: FlaskForm, action: Callable[[], object]) -> bool:
    try:
        action()
        db.session.commit()
    except (ServiceValidationError, ValueError) as error:
        db.session.rollback()
        form.form_errors.append(str(error))
        return False
    return True


@organization_blueprint.get("/")
@organization_admin_required
def index() -> str:
    return render_template("organization/index.html")


@organization_blueprint.get("/buildings")
@organization_admin_required
def buildings() -> str:
    organization_id = _organization_id()
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip()
    statement = (
        select(Building).where(Building.organization_id == organization_id).order_by(Building.name)
    )
    if search:
        pattern = f"%{search}%"
        statement = statement.where(or_(Building.name.ilike(pattern), Building.code.ilike(pattern)))
    pagination = db.paginate(
        statement,
        page=max(page, 1),
        per_page=current_app.config["MANAGEMENT_PAGE_SIZE"],
        error_out=False,
    )
    return render_template("organization/buildings.html", pagination=pagination, search=search)


@organization_blueprint.route("/buildings/new", methods=["GET", "POST"])
@organization_admin_required
def building_new() -> Any:
    form = BuildingForm()
    if form.validate_on_submit():
        created: list[Building] = []
        if _commit_or_form_error(
            form,
            lambda: created.append(
                create_building(
                    db.session,
                    organization_id=_organization_id(),
                    name=form.name.data,
                    code=form.code.data,
                    address_line=form.address_line.data,
                    district=form.district.data,
                    city=form.city.data,
                    postal_code=form.postal_code.data,
                    is_active=form.is_active.data,
                )
            ),
        ):
            flash("Bina oluşturuldu.", "success")
            return redirect(url_for("organization.building_detail", building_id=created[0].id))
    return render_template("organization/building_form.html", form=form, title="Yeni bina")


@organization_blueprint.get("/buildings/<uuid:building_id>")
@organization_admin_required
def building_detail(building_id: uuid.UUID) -> str:
    building = require_building(db.session, _organization_id(), building_id)
    return render_template("organization/building_detail.html", building=building)


@organization_blueprint.route("/buildings/<uuid:building_id>/edit", methods=["GET", "POST"])
@organization_admin_required
def building_edit(building_id: uuid.UUID) -> Any:
    try:
        building = require_building(db.session, _organization_id(), building_id)
    except ServiceValidationError:
        abort(404)
    form = BuildingForm(obj=building)
    if form.validate_on_submit() and _commit_or_form_error(
        form,
        lambda: update_building(
            db.session,
            organization_id=_organization_id(),
            building_id=building_id,
            name=form.name.data,
            code=form.code.data,
            address_line=form.address_line.data,
            district=form.district.data,
            city=form.city.data,
            postal_code=form.postal_code.data,
            is_active=form.is_active.data,
        ),
    ):
        flash("Bina güncellendi.", "success")
        return redirect(url_for("organization.building_detail", building_id=building_id))
    return render_template("organization/building_form.html", form=form, title="Bina düzenle")


@organization_blueprint.get("/buildings/<uuid:building_id>/apartments")
@organization_admin_required
def apartments(building_id: uuid.UUID) -> str:
    try:
        building = require_building(db.session, _organization_id(), building_id)
    except ServiceValidationError:
        abort(404)
    items = db.session.scalars(
        select(Apartment)
        .where(
            Apartment.organization_id == _organization_id(), Apartment.building_id == building_id
        )
        .order_by(Apartment.unit_code)
    ).all()
    return render_template("organization/apartments.html", building=building, apartments=items)


@organization_blueprint.route(
    "/buildings/<uuid:building_id>/apartments/new", methods=["GET", "POST"]
)
@organization_admin_required
def apartment_new(building_id: uuid.UUID) -> Any:
    try:
        building = require_building(db.session, _organization_id(), building_id)
    except ServiceValidationError:
        abort(404)
    form = ApartmentForm()
    if form.validate_on_submit() and _commit_or_form_error(
        form,
        lambda: create_apartment(
            db.session,
            organization_id=_organization_id(),
            building_id=building_id,
            number=form.number.data,
            floor=form.floor.data,
            block=form.block.data,
            unit_code=form.unit_code.data,
            is_active=form.is_active.data,
        ),
    ):
        flash("Daire oluşturuldu.", "success")
        return redirect(url_for("organization.apartments", building_id=building_id))
    return render_template("organization/apartment_form.html", form=form, building=building)


@organization_blueprint.route("/apartments/<uuid:apartment_id>/edit", methods=["GET", "POST"])
@organization_admin_required
def apartment_edit(apartment_id: uuid.UUID) -> Any:
    try:
        apartment = require_apartment(db.session, _organization_id(), apartment_id)
    except ServiceValidationError:
        abort(404)
    form = ApartmentForm(obj=apartment)
    if form.validate_on_submit() and _commit_or_form_error(
        form,
        lambda: update_apartment(
            db.session,
            organization_id=_organization_id(),
            apartment_id=apartment_id,
            number=form.number.data,
            floor=form.floor.data,
            block=form.block.data,
            unit_code=form.unit_code.data,
            is_active=form.is_active.data,
        ),
    ):
        flash("Daire güncellendi.", "success")
        return redirect(url_for("organization.apartments", building_id=apartment.building_id))
    return render_template(
        "organization/apartment_form.html", form=form, building=apartment.building
    )


@organization_blueprint.get("/users")
@organization_admin_required
def users() -> str:
    organization_id = _organization_id()
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip()
    statement = (
        select(User)
        .join(OrganizationMembership)
        .where(OrganizationMembership.organization_id == organization_id)
        .order_by(User.email)
    )
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                User.email.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
            )
        )
    pagination = db.paginate(
        statement,
        page=max(page, 1),
        per_page=current_app.config["MANAGEMENT_PAGE_SIZE"],
        error_out=False,
    )
    return render_template("organization/users.html", pagination=pagination, search=search)


@organization_blueprint.route("/users/new", methods=["GET", "POST"])
@organization_admin_required
def user_new() -> Any:
    form = UserForm()
    if form.validate_on_submit():

        def action() -> None:
            user, _ = resolve_or_create_user(
                db.session,
                email=form.email.data,
                first_name=form.first_name.data or "",
                last_name=form.last_name.data or "",
                phone=form.phone.data,
                temporary_password=form.temporary_password.data,
            )
            assign_organization_membership(
                db.session,
                organization_id=_organization_id(),
                user_id=user.id,
                role=OrganizationMembershipRole(form.organization_role.data),
            )

        if _commit_or_form_error(form, action):
            flash("Kullanıcı organization üyeliğine eklendi.", "success")
            return redirect(url_for("organization.users"))
    return render_template("organization/user_form.html", form=form)


@organization_blueprint.get("/users/<uuid:user_id>")
@organization_admin_required
def user_detail(user_id: uuid.UUID) -> str:
    row = db.session.execute(
        select(User, OrganizationMembership)
        .join(OrganizationMembership)
        .where(User.id == user_id, OrganizationMembership.organization_id == _organization_id())
    ).one_or_none()
    if row is None:
        abort(404)
    organization_form = _membership_form("organization")
    building_form = _membership_form("building")
    apartment_form = _membership_form("apartment")
    return render_template(
        "organization/user_detail.html",
        user=row.User,
        membership=row.OrganizationMembership,
        organization_form=organization_form,
        building_form=building_form,
        apartment_form=apartment_form,
    )


def _membership_form(kind: str) -> MembershipForm:
    form = MembershipForm()
    organization_id = _organization_id()
    if kind == "organization":
        form.set_organization_roles()
        form.resource_id.choices = []
    elif kind == "building":
        form.set_building_roles()
        form.resource_id.choices = [
            (str(item.id), f"{item.name} ({item.code})")
            for item in db.session.scalars(
                select(Building)
                .where(Building.organization_id == organization_id)
                .order_by(Building.name)
            )
        ]
    else:
        form.set_apartment_roles()
        form.resource_id.choices = [
            (str(item.id), f"{item.building.name} / {item.unit_code}")
            for item in db.session.scalars(
                select(Apartment)
                .where(Apartment.organization_id == organization_id)
                .order_by(Apartment.unit_code)
            )
        ]
    return form


def _scoped_user(user_id: uuid.UUID) -> User:
    user = db.session.scalar(
        select(User)
        .join(OrganizationMembership)
        .where(User.id == user_id, OrganizationMembership.organization_id == _organization_id())
    )
    if user is None:
        abort(404)
    return user


@organization_blueprint.post("/users/<uuid:user_id>/organization-membership")
@organization_admin_required
def organization_membership(user_id: uuid.UUID) -> Any:
    user = _scoped_user(user_id)
    form = _membership_form("organization")
    if form.validate_on_submit() and _commit_or_form_error(
        form,
        lambda: assign_organization_membership(
            db.session,
            organization_id=_organization_id(),
            user_id=user.id,
            role=OrganizationMembershipRole(form.role.data),
            starts_at=_aware(form.starts_at.data),
            ends_at=_aware(form.ends_at.data),
            is_active=form.is_active.data,
        ),
    ):
        flash("Organization üyeliği güncellendi.", "success")
    return redirect(url_for("organization.user_detail", user_id=user_id))


@organization_blueprint.post("/users/<uuid:user_id>/building-membership")
@organization_admin_required
def building_membership(user_id: uuid.UUID) -> Any:
    user = _scoped_user(user_id)
    form = _membership_form("building")
    if form.validate_on_submit() and _commit_or_form_error(
        form,
        lambda: assign_building_membership(
            db.session,
            organization_id=_organization_id(),
            building_id=uuid.UUID(form.resource_id.data),
            user_id=user.id,
            role=BuildingMembershipRole(form.role.data),
            starts_at=_aware(form.starts_at.data),
            ends_at=_aware(form.ends_at.data),
            is_active=form.is_active.data,
        ),
    ):
        flash("Bina üyeliği oluşturuldu.", "success")
    return redirect(url_for("organization.user_detail", user_id=user_id))


@organization_blueprint.post("/users/<uuid:user_id>/apartment-membership")
@organization_admin_required
def apartment_membership(user_id: uuid.UUID) -> Any:
    user = _scoped_user(user_id)
    form = _membership_form("apartment")
    if form.validate_on_submit() and _commit_or_form_error(
        form,
        lambda: assign_apartment_membership(
            db.session,
            organization_id=_organization_id(),
            apartment_id=uuid.UUID(form.resource_id.data),
            user_id=user.id,
            role=ApartmentMembershipRole(form.role.data),
            starts_at=_aware(form.starts_at.data),
            ends_at=_aware(form.ends_at.data),
            is_active=form.is_active.data,
        ),
    ):
        flash("Daire üyeliği oluşturuldu.", "success")
    return redirect(url_for("organization.user_detail", user_id=user_id))


@organization_blueprint.post("/memberships/<uuid:membership_id>/deactivate")
@organization_admin_required
def membership_deactivate(membership_id: uuid.UUID) -> Any:
    try:
        deactivate_membership(
            db.session, organization_id=_organization_id(), membership_id=membership_id
        )
        db.session.commit()
    except ServiceValidationError:
        db.session.rollback()
        abort(404)
    return redirect(request.referrer or url_for("organization.users"))

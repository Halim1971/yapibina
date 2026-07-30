from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from flask import (
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.auth.decorators import organization_admin_required
from app.blueprints.organization import organization_blueprint
from app.blueprints.organization.forms import (
    ApartmentForm,
    BuildingForm,
    ChargeBatchCreateForm,
    DuesPeriodFilterForm,
    MembershipForm,
    OrganizationBrandingForm,
    PaymentCreateForm,
    UserForm,
)
from app.extensions import db
from app.models import (
    Apartment,
    ApartmentMembershipRole,
    Building,
    BuildingMembershipRole,
    ChargeBatch,
    OrganizationMembership,
    OrganizationMembershipRole,
    PaymentMethod,
    User,
)
from app.services import ServiceValidationError
from app.services.charges import (
    cancel_charge_batch,
    create_charge_batch,
    post_charge_batch,
)
from app.services.dues_dashboard import (
    get_apartment_financial_detail,
    get_dues_dashboard,
    list_active_buildings_for_dues,
)
from app.services.organization_apartment_detail import (
    get_organization_apartment_detail,
)
from app.services.organization_branding import (
    delete_logo,
    get_effective_branding,
    resolve_logo_path,
    store_logo,
    update_organization_branding,
    validate_logo,
)
from app.services.organization_building_detail import (
    get_organization_building_detail,
)
from app.services.organization_buildings import list_organization_buildings
from app.services.organization_management import (
    create_apartment,
    create_building,
    update_apartment,
    update_building,
)
from app.services.organization_resident_detail import (
    get_organization_resident_detail,
)
from app.services.payments import auto_allocate_payment, record_payment
from app.services.resident_finances import (
    format_try,
    list_building_bank_movements,
)
from app.services.tenancy import require_apartment, require_building
from app.services.user_management import (
    assign_apartment_membership,
    assign_building_membership,
    assign_organization_membership,
    deactivate_membership,
    resolve_or_create_user,
)

logger = logging.getLogger(__name__)


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
@organization_blueprint.get("/dashboard")
@organization_admin_required
def index() -> str:
    return render_template("organization/index.html")


@organization_blueprint.get("/buildings")
@organization_admin_required
def buildings() -> str:
    listing = list_organization_buildings(
        db.session,
        organization_id=_organization_id(),
        timezone_name=current_app.config["DEFAULT_TIMEZONE"],
        search=request.args.get("q", ""),
        sort=request.args.get("sort", "name"),
        direction=request.args.get("direction", "asc"),
        page=request.args.get("page", 1, type=int) or 1,
        per_page=request.args.get(
            "per_page",
            current_app.config["MANAGEMENT_PAGE_SIZE"],
            type=int,
        )
        or current_app.config["MANAGEMENT_PAGE_SIZE"],
    )
    return render_template("organization/buildings.html", listing=listing)


@organization_blueprint.get("/bank-transactions")
@organization_admin_required
def bank_transactions() -> str:
    buildings = _dues_buildings()
    selected: Building | None = None
    requested_building = request.args.get("building_id")
    if requested_building:
        try:
            requested_id = uuid.UUID(requested_building)
        except ValueError:
            abort(404)
        selected = next(
            (building for building in buildings if building.id == requested_id),
            None,
        )
        if selected is None:
            abort(404)
    elif buildings:
        selected = buildings[0]

    page = max(request.args.get("page", 1, type=int) or 1, 1)
    per_page = request.args.get(
        "per_page",
        current_app.config["MANAGEMENT_PAGE_SIZE"],
        type=int,
    ) or current_app.config["MANAGEMENT_PAGE_SIZE"]
    per_page = per_page if per_page in {20, 50, 100} else 20
    items, total = (
        list_building_bank_movements(
            db.session,
            organization_id=_organization_id(),
            building_id=selected.id,
            page=page,
            per_page=per_page,
        )
        if selected
        else ((), 0)
    )
    return render_template(
        "organization/bank_transactions.html",
        buildings=buildings,
        selected=selected,
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        format_try=format_try,
    )


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
    try:
        detail = get_organization_building_detail(
            db.session,
            organization_id=_organization_id(),
            building_id=building_id,
            timezone_name=current_app.config["DEFAULT_TIMEZONE"],
            search=request.args.get("q", ""),
            sort=request.args.get("sort", "apartment"),
            direction=request.args.get("direction", "asc"),
            page=request.args.get("page", 1, type=int) or 1,
            per_page=request.args.get(
                "per_page",
                current_app.config["MANAGEMENT_PAGE_SIZE"],
                type=int,
            )
            or current_app.config["MANAGEMENT_PAGE_SIZE"],
        )
    except ServiceValidationError:
        abort(404)
    return render_template("organization/building_detail.html", detail=detail)


@organization_blueprint.get(
    "/buildings/<uuid:building_id>/apartments/<uuid:apartment_id>"
)
@organization_admin_required
def apartment_detail(
    building_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> str:
    page_size = current_app.config["MANAGEMENT_PAGE_SIZE"]
    try:
        detail = get_organization_apartment_detail(
            db.session,
            organization_id=_organization_id(),
            building_id=building_id,
            apartment_id=apartment_id,
            timezone_name=current_app.config["DEFAULT_TIMEZONE"],
            charge_search=request.args.get("charge_q", ""),
            charge_sort=request.args.get("charge_sort", "date"),
            charge_direction=request.args.get("charge_direction", "desc"),
            charge_page=request.args.get("charge_page", 1, type=int) or 1,
            charge_per_page=request.args.get(
                "charge_per_page", page_size, type=int
            )
            or page_size,
            payment_search=request.args.get("payment_q", ""),
            payment_sort=request.args.get("payment_sort", "date"),
            payment_direction=request.args.get("payment_direction", "desc"),
            payment_page=request.args.get("payment_page", 1, type=int) or 1,
            payment_per_page=request.args.get(
                "payment_per_page", page_size, type=int
            )
            or page_size,
            movement_page=request.args.get("movement_page", 1, type=int) or 1,
            movement_per_page=request.args.get(
                "movement_per_page", page_size, type=int
            )
            or page_size,
        )
    except ServiceValidationError:
        abort(404)
    return render_template("organization/apartment_detail.html", detail=detail)


@organization_blueprint.get("/residents/<uuid:resident_id>")
@organization_admin_required
def resident_detail(resident_id: uuid.UUID) -> str:
    page_size = current_app.config["MANAGEMENT_PAGE_SIZE"]
    selected_apartment_id = request.args.get("apartment_id", type=uuid.UUID)
    try:
        detail = get_organization_resident_detail(
            db.session,
            organization_id=_organization_id(),
            resident_id=resident_id,
            selected_apartment_id=selected_apartment_id,
            timezone_name=current_app.config["DEFAULT_TIMEZONE"],
            charge_search=request.args.get("charge_q", ""),
            charge_sort=request.args.get("charge_sort", "date"),
            charge_direction=request.args.get("charge_direction", "desc"),
            charge_page=request.args.get("charge_page", 1, type=int) or 1,
            charge_per_page=request.args.get(
                "charge_per_page", page_size, type=int
            )
            or page_size,
            payment_search=request.args.get("payment_q", ""),
            payment_sort=request.args.get("payment_sort", "date"),
            payment_direction=request.args.get("payment_direction", "desc"),
            payment_page=request.args.get("payment_page", 1, type=int) or 1,
            payment_per_page=request.args.get(
                "payment_per_page", page_size, type=int
            )
            or page_size,
            movement_page=request.args.get("movement_page", 1, type=int) or 1,
            movement_per_page=request.args.get(
                "movement_per_page", page_size, type=int
            )
            or page_size,
        )
    except ServiceValidationError:
        abort(404)
    return render_template("organization/resident_detail.html", detail=detail)


def _branding_storage_root() -> Path:
    return Path(current_app.instance_path) / "branding_assets"


@organization_blueprint.route("/settings/branding", methods=["GET", "POST"])
@organization_admin_required
def branding_settings() -> Any:
    organization_id = _organization_id()
    effective = get_effective_branding(db.session, organization_id=organization_id)
    form = OrganizationBrandingForm()
    if request.method == "GET":
        form.display_name.data = effective.display_name
        form.short_name.data = effective.short_name
        form.primary_color.data = effective.primary_color
        form.secondary_color.data = effective.secondary_color
        form.background_color.data = effective.background_color
        form.surface_color.data = effective.surface_color
        form.support_email.data = effective.support_email
        form.support_phone.data = effective.support_phone
        form.website_url.data = effective.website_url
        form.footer_text.data = effective.footer_text
        form.panel_title.data = effective.panel_title
        form.login_message.data = effective.login_message
    if form.validate_on_submit():
        current_logo = effective.logo_asset_key
        new_logo: str | None = None
        upload = form.logo.data
        try:
            if upload is not None and upload.filename:
                maximum = int(current_app.config["BRANDING_LOGO_MAX_BYTES"])
                content = upload.stream.read(maximum + 1)
                validated = validate_logo(content, maximum_bytes=maximum)
                new_logo = store_logo(
                    _branding_storage_root(),
                    organization_id=organization_id,
                    logo=validated,
                )
            update = update_organization_branding(
                db.session,
                organization_id=organization_id,
                display_name=form.display_name.data,
                short_name=form.short_name.data,
                primary_color=form.primary_color.data,
                secondary_color=form.secondary_color.data,
                background_color=form.background_color.data,
                surface_color=form.surface_color.data,
                support_email=form.support_email.data,
                support_phone=form.support_phone.data,
                website_url=form.website_url.data,
                footer_text=form.footer_text.data,
                logo_asset_key=new_logo or current_logo,
                panel_title=form.panel_title.data,
                login_message=form.login_message.data,
            )
            db.session.commit()
        except (ServiceValidationError, ValueError) as error:
            db.session.rollback()
            if new_logo is not None:
                try:
                    delete_logo(
                        _branding_storage_root(),
                        organization_id=organization_id,
                        asset_key=new_logo,
                    )
                except (OSError, ServiceValidationError):
                    logger.warning(
                        "Rejected branding logo cleanup failed",
                        extra={"organization_id": str(organization_id)},
                    )
            form.form_errors.append(str(error))
        except SQLAlchemyError:
            db.session.rollback()
            if new_logo is not None:
                try:
                    delete_logo(
                        _branding_storage_root(),
                        organization_id=organization_id,
                        asset_key=new_logo,
                    )
                except (OSError, ServiceValidationError):
                    logger.warning(
                        "Failed branding logo cleanup failed",
                        extra={"organization_id": str(organization_id)},
                    )
            logger.exception(
                "Branding update failed",
                extra={"organization_id": str(organization_id)},
            )
            raise
        else:
            if new_logo is not None and update.previous_logo_asset_key != new_logo:
                try:
                    delete_logo(
                        _branding_storage_root(),
                        organization_id=organization_id,
                        asset_key=update.previous_logo_asset_key,
                    )
                except (OSError, ServiceValidationError):
                    logger.warning(
                        "Previous branding logo cleanup failed",
                        extra={"organization_id": str(organization_id)},
                    )
            flash("Marka ayarları güncellendi.", "success")
            return redirect(url_for("organization.branding_settings"))
    return render_template(
        "organization/branding_settings.html",
        form=form,
        effective=effective,
    )


@organization_blueprint.get("/branding/logo")
def branding_logo() -> Any:
    tenant = getattr(g, "tenant", None)
    if tenant is None:
        abort(404)
    organization_id = uuid.UUID(tenant.organization_id)
    effective = get_effective_branding(db.session, organization_id=organization_id)
    if effective.logo_asset_key is None:
        abort(404)
    try:
        path = resolve_logo_path(
            _branding_storage_root(),
            organization_id=organization_id,
            asset_key=effective.logo_asset_key,
        )
    except ServiceValidationError:
        abort(404)
    if not path.is_file():
        abort(404)
    return send_file(path, conditional=True, max_age=3600)


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
        flash("Bağımsız bölüm oluşturuldu.", "success")
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
        flash("Bağımsız bölüm güncellendi.", "success")
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
        flash("Bağımsız bölüm üyeliği oluşturuldu.", "success")
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


def _dues_buildings() -> list[Building]:
    return list_active_buildings_for_dues(
        db.session,
        organization_id=_organization_id(),
    )


def _dues_choices(buildings: list[Building]) -> list[tuple[str, str]]:
    return [(str(building.id), building.name) for building in buildings]


def _dues_redirect(building_id: uuid.UUID, year: int, month: int) -> Any:
    return redirect(
        url_for(
            "organization.dues",
            building_id=building_id,
            year=year,
            month=month,
        )
    )


@organization_blueprint.get("/dues")
@organization_admin_required
def dues() -> Any:
    buildings = _dues_buildings()
    today = date.today()
    selected: Building | None = None
    requested_building = request.args.get("building_id")
    if requested_building:
        try:
            requested_id = uuid.UUID(requested_building)
        except ValueError:
            abort(404)
        selected = next(
            (building for building in buildings if building.id == requested_id),
            None,
        )
        if selected is None:
            abort(404)
    elif buildings:
        selected = buildings[0]

    period_form = DuesPeriodFilterForm(request.args)
    choices = _dues_choices(buildings)
    period_form.set_choices(choices, today.year)
    if not request.args:
        period_form.building_id.data = str(selected.id) if selected else None
        period_form.year.data = today.year
        period_form.month.data = today.month
    if request.args and not period_form.validate():
        flash("Bina veya dönem seçimi geçerli değil.", "error")
        year, month = today.year, today.month
    else:
        year = period_form.year.data or today.year
        month = period_form.month.data or today.month

    dashboard = get_dues_dashboard(
        db.session,
        organization_id=_organization_id(),
        building=selected,
        year=year,
        month=month,
    )
    return render_template(
        "organization/dues/index.html",
        dashboard=dashboard,
        period_form=period_form,
    )


@organization_blueprint.post("/dues/batches")
@organization_admin_required
def dues_batch_create() -> Any:
    buildings = _dues_buildings()
    today = date.today()
    form = ChargeBatchCreateForm()
    form.set_choices(_dues_choices(buildings), today.year)
    try:
        building_id = uuid.UUID(request.form.get("building_id", ""))
    except ValueError:
        abort(404)
    if not any(building.id == building_id for building in buildings):
        abort(404)
    if not form.validate_on_submit():
        flash("Aidat bilgilerini kontrol edin.", "error")
        return redirect(url_for("organization.dues"))
    try:
        batch = create_charge_batch(
            db.session,
            organization_id=_organization_id(),
            building_id=building_id,
            period_year=form.period_year.data,
            period_month=form.period_month.data,
            title=form.title.data,
            description=form.description.data,
            default_amount=form.default_amount.data,
            due_date=form.due_date.data,
            created_by_user_id=current_user.id,
        )
        post_charge_batch(
            db.session,
            organization_id=_organization_id(),
            batch_id=batch.id,
        )
        db.session.commit()
    except ServiceValidationError as error:
        db.session.rollback()
        flash(str(error), "error")
    else:
        flash("Aidatlar tüm aktif bağımsız bölümler için oluşturuldu.", "success")
    return _dues_redirect(
        building_id,
        form.period_year.data,
        form.period_month.data,
    )


@organization_blueprint.post("/dues/batches/<uuid:batch_id>/post")
@organization_admin_required
def dues_batch_post(batch_id: uuid.UUID) -> Any:
    batch = db.session.scalar(
        select(ChargeBatch).where(
            ChargeBatch.id == batch_id,
            ChargeBatch.organization_id == _organization_id(),
        )
    )
    if batch is None:
        abort(404)
    try:
        post_charge_batch(
            db.session,
            organization_id=_organization_id(),
            batch_id=batch.id,
        )
        db.session.commit()
    except ServiceValidationError as error:
        db.session.rollback()
        flash(str(error), "error")
    else:
        flash("Aidatlar başlatıldı.", "success")
    return _dues_redirect(batch.building_id, batch.period_year, batch.period_month)


@organization_blueprint.post("/dues/batches/<uuid:batch_id>/cancel")
@organization_admin_required
def dues_batch_cancel(batch_id: uuid.UUID) -> Any:
    batch = db.session.scalar(
        select(ChargeBatch).where(
            ChargeBatch.id == batch_id,
            ChargeBatch.organization_id == _organization_id(),
        )
    )
    if batch is None:
        abort(404)
    try:
        cancel_charge_batch(
            db.session,
            organization_id=_organization_id(),
            batch_id=batch.id,
            reason=request.form.get("reason", ""),
        )
        db.session.commit()
    except ServiceValidationError as error:
        db.session.rollback()
        flash(str(error), "error")
    else:
        flash("Aidatlar iptal edildi.", "success")
    return _dues_redirect(batch.building_id, batch.period_year, batch.period_month)


@organization_blueprint.get("/dues/apartments/<uuid:apartment_id>")
@organization_admin_required
def dues_apartment_detail(apartment_id: uuid.UUID) -> Any:
    try:
        detail = get_apartment_financial_detail(
            db.session,
            organization_id=_organization_id(),
            apartment_id=apartment_id,
        )
    except ServiceValidationError:
        abort(404)
    return render_template(
        "organization/dues/apartment_detail.html",
        detail=detail,
        payment_form=PaymentCreateForm(),
    )


@organization_blueprint.post(
    "/dues/apartments/<uuid:apartment_id>/payments"
)
@organization_admin_required
def dues_payment_create(apartment_id: uuid.UUID) -> Any:
    try:
        apartment = require_apartment(
            db.session,
            _organization_id(),
            apartment_id,
        )
    except ServiceValidationError:
        abort(404)
    form = PaymentCreateForm()
    if not form.validate_on_submit():
        flash("Ödeme bilgilerini kontrol edin.", "error")
        return redirect(
            url_for(
                "organization.dues_apartment_detail",
                apartment_id=apartment.id,
            )
        )
    try:
        payment = record_payment(
            db.session,
            organization_id=_organization_id(),
            building_id=apartment.building_id,
            apartment_id=apartment.id,
            amount=form.amount.data,
            payment_date=form.payment_date.data,
            payment_method=PaymentMethod(form.payment_method.data),
            recorded_by_user_id=current_user.id,
            reference=form.reference.data,
            description=form.description.data,
        )
        if form.auto_allocate.data:
            auto_allocate_payment(
                db.session,
                organization_id=_organization_id(),
                payment_id=payment.id,
            )
        db.session.commit()
    except ServiceValidationError as error:
        db.session.rollback()
        flash(str(error), "error")
    else:
        message = "Ödeme kaydedildi."
        if form.auto_allocate.data:
            message += " Ödeme en eski açık borçtan başlayarak işlendi."
        flash(message, "success")
    return redirect(
        url_for(
            "organization.dues_apartment_detail",
            apartment_id=apartment.id,
        )
    )

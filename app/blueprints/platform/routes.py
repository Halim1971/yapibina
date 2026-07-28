from __future__ import annotations

import uuid
from typing import Any

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import or_, select

from app.auth.decorators import platform_admin_required
from app.blueprints.platform import platform_blueprint
from app.blueprints.platform.forms import (
    BrandingForm,
    DomainForm,
    OrganizationAdminForm,
    OrganizationForm,
)
from app.extensions import db
from app.models import (
    DomainState,
    DomainType,
    Organization,
    OrganizationBranding,
    OrganizationDomain,
    OrganizationMembership,
    OrganizationMembershipRole,
    OrganizationStatus,
    User,
)
from app.services import ServiceValidationError
from app.services.domain_management import create_domain, make_primary, transition_domain
from app.services.platform_management import (
    create_organization,
    update_branding,
    update_organization,
)
from app.services.user_management import (
    assign_organization_membership,
    resolve_or_create_user,
)


def _organization_or_404(organization_id: uuid.UUID) -> Organization:
    organization = db.session.get(Organization, organization_id)
    if organization is None:
        abort(404)
    return organization


@platform_blueprint.get("/")
@platform_admin_required
def index() -> str:
    return render_template("platform/index.html")


@platform_blueprint.get("/organizations")
@platform_admin_required
def organizations() -> str:
    page = request.args.get("page", 1, type=int)
    search = request.args.get("q", "").strip()
    statement = select(Organization).order_by(Organization.name)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(Organization.name.ilike(pattern), Organization.slug.ilike(pattern))
        )
    pagination = db.paginate(
        statement,
        page=max(page, 1),
        per_page=current_app.config["MANAGEMENT_PAGE_SIZE"],
        error_out=False,
    )
    return render_template(
        "platform/organizations.html",
        pagination=pagination,
        search=search,
    )


@platform_blueprint.route("/organizations/new", methods=["GET", "POST"])
@platform_admin_required
def organization_new() -> Any:
    form = OrganizationForm()
    if form.validate_on_submit():
        try:
            organization = create_organization(
                db.session,
                name=form.name.data,
                legal_name=form.legal_name.data,
                slug=form.slug.data,
                status=OrganizationStatus(form.status.data),
                support_email=form.support_email.data,
                phone=form.phone.data,
                website=form.website.data,
            )
            db.session.commit()
        except (ServiceValidationError, ValueError) as error:
            db.session.rollback()
            form.slug.errors.append(str(error))
        else:
            flash("Organization oluşturuldu.", "success")
            return redirect(
                url_for("platform.organization_detail", organization_id=organization.id)
            )
    return render_template("platform/organization_form.html", form=form, title="Yeni organization")


@platform_blueprint.get("/organizations/<uuid:organization_id>")
@platform_admin_required
def organization_detail(organization_id: uuid.UUID) -> str:
    return render_template(
        "platform/organization_detail.html",
        organization=_organization_or_404(organization_id),
    )


@platform_blueprint.route("/organizations/<uuid:organization_id>/edit", methods=["GET", "POST"])
@platform_admin_required
def organization_edit(organization_id: uuid.UUID) -> Any:
    organization = _organization_or_404(organization_id)
    form = OrganizationForm(obj=organization)
    if form.validate_on_submit():
        try:
            update_organization(
                db.session,
                organization_id=organization_id,
                name=form.name.data,
                legal_name=form.legal_name.data,
                slug=form.slug.data,
                status=OrganizationStatus(form.status.data),
                support_email=form.support_email.data,
                phone=form.phone.data,
                website=form.website.data,
            )
            db.session.commit()
        except (ServiceValidationError, ValueError) as error:
            db.session.rollback()
            form.slug.errors.append(str(error))
        else:
            flash("Organization güncellendi.", "success")
            return redirect(
                url_for("platform.organization_detail", organization_id=organization_id)
            )
    return render_template(
        "platform/organization_form.html", form=form, title="Organization düzenle"
    )


@platform_blueprint.route("/organizations/<uuid:organization_id>/branding", methods=["GET", "POST"])
@platform_admin_required
def branding(organization_id: uuid.UUID) -> Any:
    organization = _organization_or_404(organization_id)
    current = db.session.scalar(
        select(OrganizationBranding).where(OrganizationBranding.organization_id == organization_id)
    )
    form = BrandingForm(obj=current)
    if form.validate_on_submit():
        update_branding(
            db.session,
            organization_id=organization_id,
            company_display_name=form.company_display_name.data,
            primary_color=form.primary_color.data,
            secondary_color=form.secondary_color.data,
            surface_color=form.surface_color.data,
            panel_title=form.panel_title.data,
            login_message=form.login_message.data,
            white_label_enabled=form.white_label_enabled.data,
        )
        db.session.commit()
        flash("Marka ayarları güncellendi.", "success")
        return redirect(url_for("platform.branding", organization_id=organization_id))
    return render_template("platform/branding.html", form=form, organization=organization)


@platform_blueprint.get("/organizations/<uuid:organization_id>/domains")
@platform_admin_required
def domains(organization_id: uuid.UUID) -> str:
    organization = _organization_or_404(organization_id)
    items = db.session.scalars(
        select(OrganizationDomain)
        .where(OrganizationDomain.organization_id == organization_id)
        .order_by(OrganizationDomain.hostname)
    ).all()
    return render_template("platform/domains.html", organization=organization, domains=items)


@platform_blueprint.route(
    "/organizations/<uuid:organization_id>/domains/new", methods=["GET", "POST"]
)
@platform_admin_required
def domain_new(organization_id: uuid.UUID) -> Any:
    organization = _organization_or_404(organization_id)
    form = DomainForm()
    if form.validate_on_submit():
        try:
            create_domain(
                db.session,
                organization_id=organization_id,
                hostname=form.hostname.data,
                domain_type=DomainType(form.domain_type.data),
                is_primary=form.is_primary.data,
            )
            db.session.commit()
        except (ServiceValidationError, ValueError) as error:
            db.session.rollback()
            form.hostname.errors.append(str(error))
        else:
            flash("Domain awaiting_dns durumunda oluşturuldu.", "success")
            return redirect(url_for("platform.domains", organization_id=organization_id))
    return render_template("platform/domain_form.html", form=form, organization=organization)


def _domain_action(
    organization_id: uuid.UUID,
    domain_id: uuid.UUID,
    target: DomainState | None,
) -> Any:
    _organization_or_404(organization_id)
    try:
        if target is None:
            make_primary(db.session, organization_id=organization_id, domain_id=domain_id)
        else:
            transition_domain(
                db.session,
                organization_id=organization_id,
                domain_id=domain_id,
                target=target,
            )
        db.session.commit()
    except ServiceValidationError as error:
        db.session.rollback()
        abort(400, description=str(error))
    flash("Domain güncellendi.", "success")
    return redirect(url_for("platform.domains", organization_id=organization_id))


@platform_blueprint.post("/organizations/<uuid:organization_id>/domains/<uuid:domain_id>/primary")
@platform_admin_required
def domain_primary(organization_id: uuid.UUID, domain_id: uuid.UUID) -> Any:
    return _domain_action(organization_id, domain_id, None)


@platform_blueprint.post("/organizations/<uuid:organization_id>/domains/<uuid:domain_id>/activate")
@platform_admin_required
def domain_activate(organization_id: uuid.UUID, domain_id: uuid.UUID) -> Any:
    domain = db.session.scalar(
        select(OrganizationDomain).where(
            OrganizationDomain.id == domain_id,
            OrganizationDomain.organization_id == organization_id,
        )
    )
    if domain is None:
        abort(404)
    target = DomainState.ACTIVE
    return _domain_action(organization_id, domain_id, target)


@platform_blueprint.post("/organizations/<uuid:organization_id>/domains/<uuid:domain_id>/suspend")
@platform_admin_required
def domain_suspend(organization_id: uuid.UUID, domain_id: uuid.UUID) -> Any:
    return _domain_action(organization_id, domain_id, DomainState.SUSPENDED)


@platform_blueprint.route("/organizations/<uuid:organization_id>/admins", methods=["GET", "POST"])
@platform_admin_required
def admins(organization_id: uuid.UUID) -> Any:
    organization = _organization_or_404(organization_id)
    form = OrganizationAdminForm()
    if form.validate_on_submit():
        try:
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
                organization_id=organization_id,
                user_id=user.id,
                role=OrganizationMembershipRole.ORGANIZATION_ADMIN,
            )
            db.session.commit()
        except (ServiceValidationError, ValueError) as error:
            db.session.rollback()
            form.email.errors.append(str(error))
        else:
            flash("Organization admin atandı.", "success")
            return redirect(url_for("platform.admins", organization_id=organization_id))
    admin_rows = db.session.execute(
        select(User, OrganizationMembership)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.role == OrganizationMembershipRole.ORGANIZATION_ADMIN,
        )
    ).all()
    return render_template(
        "platform/admins.html",
        form=form,
        organization=organization,
        admin_rows=admin_rows,
    )

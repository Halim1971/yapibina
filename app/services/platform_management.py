from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Organization, OrganizationBranding, OrganizationStatus
from app.models.base import normalize_slug
from app.services import DuplicateEntityError, SessionLike
from app.services.tenancy import require_organization


def create_organization(
    session: SessionLike,
    *,
    name: str,
    legal_name: str | None,
    slug: str,
    status: OrganizationStatus,
    support_email: str | None,
    phone: str | None,
    website: str | None,
) -> Organization:
    normalized_slug = normalize_slug(slug)
    if session.scalar(select(Organization.id).where(Organization.slug == normalized_slug)):
        raise DuplicateEntityError("Bu organization slug değeri zaten kullanılıyor.")
    organization = Organization(
        name=name.strip(),
        legal_name=legal_name or None,
        slug=normalized_slug,
        status=status,
        support_email=support_email or None,
        phone=phone or None,
        website=website or None,
    )
    session.add(organization)
    try:
        session.flush()
        session.add(OrganizationBranding(organization_id=organization.id))
        session.flush()
    except IntegrityError as error:
        raise DuplicateEntityError("Bu organization slug değeri zaten kullanılıyor.") from error
    return organization


def update_organization(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    name: str,
    legal_name: str | None,
    slug: str,
    status: OrganizationStatus,
    support_email: str | None,
    phone: str | None,
    website: str | None,
) -> Organization:
    organization = require_organization(session, organization_id)
    normalized_slug = normalize_slug(slug)
    duplicate = session.scalar(
        select(Organization.id).where(
            Organization.slug == normalized_slug,
            Organization.id != organization_id,
        )
    )
    if duplicate:
        raise DuplicateEntityError("Bu organization slug değeri zaten kullanılıyor.")
    organization.name = name.strip()
    organization.legal_name = legal_name or None
    organization.slug = normalized_slug
    organization.status = status
    organization.support_email = support_email or None
    organization.phone = phone or None
    organization.website = website or None
    try:
        session.flush()
    except IntegrityError as error:
        raise DuplicateEntityError("Bu organization slug değeri zaten kullanılıyor.") from error
    return organization


def update_branding(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    company_display_name: str | None,
    primary_color: str | None,
    secondary_color: str | None,
    surface_color: str | None,
    panel_title: str | None,
    login_message: str | None,
    white_label_enabled: bool,
) -> OrganizationBranding:
    require_organization(session, organization_id)
    branding = session.scalar(
        select(OrganizationBranding).where(OrganizationBranding.organization_id == organization_id)
    )
    if branding is None:
        branding = OrganizationBranding(organization_id=organization_id)
        session.add(branding)
    branding.company_display_name = company_display_name or None
    branding.primary_color = primary_color or None
    branding.secondary_color = secondary_color or None
    branding.surface_color = surface_color or None
    branding.panel_title = panel_title or None
    branding.login_message = login_message or None
    branding.white_label_enabled = white_label_enabled
    session.flush()
    return branding

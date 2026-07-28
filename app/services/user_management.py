from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select

from app.models import (
    ApartmentMembership,
    ApartmentMembershipRole,
    BuildingMembership,
    BuildingMembershipRole,
    OrganizationMembership,
    OrganizationMembershipRole,
    User,
)
from app.models.base import normalize_email, utc_now
from app.services import EntityNotFoundError, SessionLike
from app.services.memberships import (
    create_apartment_membership,
    create_building_membership,
    create_organization_membership,
    validate_membership_period,
)


def resolve_or_create_user(
    session: SessionLike,
    *,
    email: str,
    first_name: str,
    last_name: str,
    phone: str | None,
    temporary_password: str | None,
) -> tuple[User, bool]:
    normalized = normalize_email(email)
    user = session.scalar(select(User).where(User.email == normalized))
    if user is not None:
        return user, False
    if not temporary_password:
        from app.services import ServiceValidationError

        raise ServiceValidationError("Yeni kullanıcı için geçici parola zorunludur.")
    user = User(
        email=normalized,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        phone=phone or None,
        password_hash="",
        is_platform_super_admin=False,
    )
    user.set_password(temporary_password)
    session.add(user)
    session.flush()
    return user, True


def assign_organization_membership(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role: OrganizationMembershipRole,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    is_active: bool = True,
) -> OrganizationMembership:
    existing = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    if existing is None:
        existing = create_organization_membership(
            session,
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            starts_at=starts_at,
            ends_at=ends_at,
        )
    else:
        effective_start = starts_at or existing.starts_at
        validate_membership_period(effective_start, ends_at)
        existing.role = role
        existing.starts_at = effective_start
        existing.ends_at = ends_at
    existing.is_active = is_active
    session.flush()
    return existing


def assign_building_membership(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    user_id: uuid.UUID,
    role: BuildingMembershipRole,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    is_active: bool = True,
) -> BuildingMembership:
    membership = create_building_membership(
        session,
        organization_id=organization_id,
        building_id=building_id,
        user_id=user_id,
        role=role,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    membership.is_active = is_active
    session.flush()
    return membership


def assign_apartment_membership(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
    user_id: uuid.UUID,
    role: ApartmentMembershipRole,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    is_active: bool = True,
) -> ApartmentMembership:
    membership = create_apartment_membership(
        session,
        organization_id=organization_id,
        apartment_id=apartment_id,
        user_id=user_id,
        role=role,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    membership.is_active = is_active
    session.flush()
    return membership


def deactivate_membership(
    session: SessionLike, *, organization_id: uuid.UUID, membership_id: uuid.UUID
) -> object:
    organization_membership = session.get(OrganizationMembership, membership_id)
    building_membership = session.get(BuildingMembership, membership_id)
    apartment_membership = session.get(ApartmentMembership, membership_id)
    membership = organization_membership or building_membership or apartment_membership
    if membership is not None:
        if membership.organization_id != organization_id:
            raise EntityNotFoundError("Üyelik bulunamadı.")
        membership.is_active = False
        if membership.ends_at is None:
            membership.ends_at = utc_now()
        session.flush()
        return membership
    raise EntityNotFoundError("Üyelik bulunamadı.")

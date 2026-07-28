from __future__ import annotations

import uuid

from sqlalchemy import or_, select

from app.models import (
    Apartment,
    ApartmentMembership,
    Building,
    BuildingMembership,
    BuildingMembershipRole,
    OrganizationMembership,
    OrganizationMembershipRole,
    User,
    UserStatus,
)
from app.models.base import utc_now
from app.services import SessionLike
from app.tenant.resolver import TenantContext


def is_active_user(user: User) -> bool:
    return user.status is UserStatus.ACTIVE


def can_access_platform(
    user: User,
    *,
    tenant: TenantContext | None,
    is_platform_request: bool,
) -> bool:
    return (
        is_active_user(user)
        and is_platform_request
        and tenant is None
        and user.is_platform_super_admin
    )


def effective_organization_membership(
    session: SessionLike,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> OrganizationMembership | None:
    now = utc_now()
    return session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.starts_at <= now,
            or_(
                OrganizationMembership.ends_at.is_(None),
                OrganizationMembership.ends_at >= now,
            ),
        )
    )


def scoped_building(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
) -> Building | None:
    return session.scalar(
        select(Building).where(
            Building.id == building_id,
            Building.organization_id == organization_id,
            Building.is_active.is_(True),
        )
    )


def can_access_building(
    session: SessionLike,
    *,
    user: User,
    organization_id: uuid.UUID,
    building: Building,
) -> bool:
    membership = effective_organization_membership(
        session,
        user_id=user.id,
        organization_id=organization_id,
    )
    if membership is None:
        return False
    if membership.role is OrganizationMembershipRole.ORGANIZATION_ADMIN:
        return True

    now = utc_now()
    assignment = session.scalar(
        select(BuildingMembership.id).where(
            BuildingMembership.organization_id == organization_id,
            BuildingMembership.building_id == building.id,
            BuildingMembership.user_id == user.id,
            BuildingMembership.role == BuildingMembershipRole.BUILDING_MANAGER,
            BuildingMembership.is_active.is_(True),
            BuildingMembership.starts_at <= now,
            or_(
                BuildingMembership.ends_at.is_(None),
                BuildingMembership.ends_at >= now,
            ),
        )
    )
    return assignment is not None


def scoped_apartment(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> Apartment | None:
    return session.scalar(
        select(Apartment).where(
            Apartment.id == apartment_id,
            Apartment.organization_id == organization_id,
            Apartment.is_active.is_(True),
        )
    )


def can_access_apartment(
    session: SessionLike,
    *,
    user: User,
    organization_id: uuid.UUID,
    apartment: Apartment,
) -> bool:
    now = utc_now()
    membership = session.scalar(
        select(ApartmentMembership.id).where(
            ApartmentMembership.organization_id == organization_id,
            ApartmentMembership.apartment_id == apartment.id,
            ApartmentMembership.user_id == user.id,
            ApartmentMembership.is_active.is_(True),
            ApartmentMembership.starts_at <= now,
            or_(
                ApartmentMembership.ends_at.is_(None),
                ApartmentMembership.ends_at >= now,
            ),
        )
    )
    return membership is not None


def has_resident_access(
    session: SessionLike,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> bool:
    now = utc_now()
    membership = session.scalar(
        select(ApartmentMembership.id).where(
            ApartmentMembership.organization_id == organization_id,
            ApartmentMembership.user_id == user_id,
            ApartmentMembership.is_active.is_(True),
            ApartmentMembership.starts_at <= now,
            or_(
                ApartmentMembership.ends_at.is_(None),
                ApartmentMembership.ends_at >= now,
            ),
        )
    )
    return membership is not None

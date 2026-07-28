from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select

from app.models import (
    ApartmentMembership,
    ApartmentMembershipRole,
    BuildingMembership,
    BuildingMembershipRole,
    OrganizationMembership,
    OrganizationMembershipRole,
)
from app.models.base import as_utc, utc_now
from app.services import MembershipOverlapError, ServiceValidationError, SessionLike
from app.services.tenancy import (
    require_apartment,
    require_building,
    require_organization,
    require_user,
)


def _validate_period(starts_at: datetime, ends_at: datetime | None) -> None:
    if starts_at.tzinfo is None or (ends_at is not None and ends_at.tzinfo is None):
        raise ServiceValidationError("Membership timestamps must be timezone-aware.")
    if ends_at is not None and as_utc(ends_at) < as_utc(starts_at):
        raise ServiceValidationError("Membership end cannot precede its start.")


def create_organization_membership(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role: OrganizationMembershipRole,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> OrganizationMembership:
    start = starts_at or utc_now()
    _validate_period(start, ends_at)
    require_organization(session, organization_id)
    require_user(session, user_id)
    existing = session.scalar(
        select(OrganizationMembership.id).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )
    if existing is not None:
        raise MembershipOverlapError(
            "User already has an organization membership."
        )
    membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        starts_at=start,
        ends_at=ends_at,
    )
    session.add(membership)
    return membership


def create_building_membership(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    user_id: uuid.UUID,
    role: BuildingMembershipRole,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> BuildingMembership:
    start = starts_at or utc_now()
    _validate_period(start, ends_at)
    require_organization(session, organization_id)
    require_user(session, user_id)
    require_building(session, organization_id, building_id)
    existing = session.scalar(
        select(BuildingMembership.id).where(
            BuildingMembership.building_id == building_id,
            BuildingMembership.user_id == user_id,
            BuildingMembership.is_active.is_(True),
        )
    )
    if existing is not None:
        raise MembershipOverlapError("Active building membership already exists.")
    membership = BuildingMembership(
        organization_id=organization_id,
        building_id=building_id,
        user_id=user_id,
        role=role,
        starts_at=start,
        ends_at=ends_at,
    )
    session.add(membership)
    return membership


def create_apartment_membership(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
    user_id: uuid.UUID,
    role: ApartmentMembershipRole,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> ApartmentMembership:
    start = starts_at or utc_now()
    _validate_period(start, ends_at)
    require_organization(session, organization_id)
    require_user(session, user_id)
    require_apartment(session, organization_id, apartment_id)

    overlap_conditions = [
        ApartmentMembership.apartment_id == apartment_id,
        ApartmentMembership.user_id == user_id,
        ApartmentMembership.is_active.is_(True),
        or_(
            ApartmentMembership.ends_at.is_(None),
            ApartmentMembership.ends_at >= start,
        ),
    ]
    if ends_at is not None:
        overlap_conditions.append(ApartmentMembership.starts_at <= ends_at)

    existing = session.scalar(
        select(ApartmentMembership.id).where(and_(*overlap_conditions))
    )
    if existing is not None:
        raise MembershipOverlapError("Apartment membership period overlaps.")

    membership = ApartmentMembership(
        organization_id=organization_id,
        apartment_id=apartment_id,
        user_id=user_id,
        role=role,
        starts_at=start,
        ends_at=ends_at,
    )
    session.add(membership)
    return membership

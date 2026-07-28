from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select

from app.models import (
    ApartmentMembership,
    BuildingMembership,
    OrganizationMembership,
    OrganizationMembershipRole,
    User,
    UserStatus,
)
from app.models.base import normalize_email, utc_now
from app.services import SessionLike
from app.tenant.resolver import TenantContext


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    user: User
    destination: str


def _effective_at(model: type[OrganizationMembership], now: datetime) -> list[object]:
    return [
        model.is_active.is_(True),
        model.starts_at <= now,
        or_(model.ends_at.is_(None), model.ends_at >= now),
    ]


def _tenant_destination(
    session: SessionLike,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    membership: OrganizationMembership,
    now: datetime,
) -> str:
    if membership.role is OrganizationMembershipRole.ORGANIZATION_ADMIN:
        return "/organization/"
    building_access = session.scalar(
        select(BuildingMembership.id).where(
            BuildingMembership.organization_id == organization_id,
            BuildingMembership.user_id == user_id,
            BuildingMembership.is_active.is_(True),
            BuildingMembership.starts_at <= now,
            or_(
                BuildingMembership.ends_at.is_(None),
                BuildingMembership.ends_at >= now,
            ),
        )
    )
    if building_access is not None:
        return "/organization/"
    resident_access = session.scalar(
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
    return "/resident/" if resident_access is not None else "/organization/"


def authenticate_user(
    session: SessionLike,
    *,
    email: str,
    password: str,
    tenant: TenantContext | None,
    is_platform_request: bool,
) -> AuthenticationResult | None:
    normalized_email = normalize_email(email)
    user = session.scalar(select(User).where(User.email == normalized_email))
    if (
        user is None
        or user.status is not UserStatus.ACTIVE
        or not user.check_password(password)
    ):
        return None

    if is_platform_request:
        if tenant is not None or not user.is_platform_super_admin:
            return None
        return AuthenticationResult(user=user, destination="/platform/")

    if tenant is None or user.is_platform_super_admin:
        return None

    organization_id = uuid.UUID(tenant.organization_id)
    now = utc_now()
    membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.starts_at <= now,
            or_(
                OrganizationMembership.ends_at.is_(None),
                OrganizationMembership.ends_at >= now,
            ),
        )
    )
    if membership is None:
        return None
    destination = _tenant_destination(
        session,
        user.id,
        organization_id,
        membership,
        now,
    )
    return AuthenticationResult(user=user, destination=destination)

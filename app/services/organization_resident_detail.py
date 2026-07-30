from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, func, or_, select

from app.models import (
    Apartment,
    ApartmentMembership,
    Building,
    Organization,
    OrganizationMembership,
    User,
    UserStatus,
)
from app.services import ServiceValidationError, SessionLike
from app.services.organization_apartment_detail import (
    OrganizationApartmentDetail,
    get_organization_apartment_detail,
)


@dataclass(frozen=True, slots=True)
class ResidentIdentity:
    id: uuid.UUID
    display_name: str
    first_name: str
    last_name: str
    email: str
    phone: str | None
    is_active: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ResidentPlacement:
    membership_id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    building_id: uuid.UUID
    building_name: str
    apartment_id: uuid.UUID
    apartment_label: str
    block: str | None
    floor: str | None
    role_label: str
    starts_at: datetime


@dataclass(frozen=True, slots=True)
class OrganizationResidentDetail:
    resident: ResidentIdentity
    placements: tuple[ResidentPlacement, ...]
    selected_placement: ResidentPlacement | None
    apartment_finance: OrganizationApartmentDetail | None


def _resident_identity(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    resident_id: uuid.UUID,
    timezone_name: str,
) -> ResidentIdentity:
    has_apartment_membership = exists(
        select(ApartmentMembership.id).where(
            ApartmentMembership.organization_id == organization_id,
            ApartmentMembership.user_id == resident_id,
        )
    )
    row = session.execute(
        select(User)
        .join(
            OrganizationMembership,
            and_(
                OrganizationMembership.user_id == User.id,
                OrganizationMembership.organization_id == organization_id,
            ),
        )
        .where(
            User.id == resident_id,
            has_apartment_membership,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ServiceValidationError("İkamet eden bulunamadı.")

    return ResidentIdentity(
        id=row.id,
        display_name=f"{row.first_name} {row.last_name}".strip() or row.email,
        first_name=row.first_name,
        last_name=row.last_name,
        email=row.email,
        phone=row.phone,
        is_active=row.is_active,
        created_at=(
            row.created_at
            if row.created_at.tzinfo is not None
            else row.created_at.replace(tzinfo=timezone.utc)
        ).astimezone(ZoneInfo(timezone_name)),
    )


def _active_placements(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    resident_id: uuid.UUID,
    now: datetime,
    timezone_name: str,
) -> tuple[ResidentPlacement, ...]:
    rows = session.execute(
        select(ApartmentMembership, Apartment, Building, Organization)
        .join(
            Apartment,
            and_(
                Apartment.id == ApartmentMembership.apartment_id,
                Apartment.organization_id == organization_id,
            ),
        )
        .join(
            Building,
            and_(
                Building.id == Apartment.building_id,
                Building.organization_id == organization_id,
            ),
        )
        .join(Organization, Organization.id == organization_id)
        .join(
            OrganizationMembership,
            and_(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == resident_id,
            ),
        )
        .join(User, User.id == resident_id)
        .where(
            ApartmentMembership.organization_id == organization_id,
            ApartmentMembership.user_id == resident_id,
            ApartmentMembership.is_active.is_(True),
            ApartmentMembership.starts_at <= now,
            or_(
                ApartmentMembership.ends_at.is_(None),
                ApartmentMembership.ends_at >= now,
            ),
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            User.status == UserStatus.ACTIVE,
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.starts_at <= now,
            or_(
                OrganizationMembership.ends_at.is_(None),
                OrganizationMembership.ends_at >= now,
            ),
        )
        .order_by(
            Building.name,
            func.length(func.coalesce(Apartment.unit_code, Apartment.number)),
            func.coalesce(Apartment.unit_code, Apartment.number),
            ApartmentMembership.id,
        )
    ).all()
    return tuple(
        ResidentPlacement(
            membership_id=row.ApartmentMembership.id,
            organization_id=organization_id,
            organization_name=row.Organization.name,
            building_id=row.Building.id,
            building_name=row.Building.name,
            apartment_id=row.Apartment.id,
            apartment_label=row.Apartment.unit_code or row.Apartment.number,
            block=row.Apartment.block,
            floor=row.Apartment.floor,
            role_label=row.ApartmentMembership.role.value,
            starts_at=(
                row.ApartmentMembership.starts_at
                if row.ApartmentMembership.starts_at.tzinfo is not None
                else row.ApartmentMembership.starts_at.replace(tzinfo=timezone.utc)
            ).astimezone(ZoneInfo(timezone_name)),
        )
        for row in rows
    )


def get_organization_resident_detail(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    resident_id: uuid.UUID,
    timezone_name: str,
    selected_apartment_id: uuid.UUID | None = None,
    charge_search: str = "",
    charge_sort: str = "date",
    charge_direction: str = "desc",
    charge_page: int = 1,
    charge_per_page: int = 20,
    payment_search: str = "",
    payment_sort: str = "date",
    payment_direction: str = "desc",
    payment_page: int = 1,
    payment_per_page: int = 20,
    movement_page: int = 1,
    movement_per_page: int = 20,
) -> OrganizationResidentDetail:
    resident = _resident_identity(
        session,
        organization_id=organization_id,
        resident_id=resident_id,
        timezone_name=timezone_name,
    )
    placements = _active_placements(
        session,
        organization_id=organization_id,
        resident_id=resident_id,
        now=datetime.now(timezone.utc),
        timezone_name=timezone_name,
    )
    selected = next(
        (
            placement
            for placement in placements
            if placement.apartment_id == selected_apartment_id
        ),
        None,
    )
    if selected_apartment_id is not None and selected is None:
        raise ServiceValidationError("Aktif bağımsız bölüm bağlantısı bulunamadı.")
    if selected is None and placements:
        selected = placements[0]

    apartment_finance = (
        get_organization_apartment_detail(
            session,
            organization_id=organization_id,
            building_id=selected.building_id,
            apartment_id=selected.apartment_id,
            timezone_name=timezone_name,
            charge_search=charge_search,
            charge_sort=charge_sort,
            charge_direction=charge_direction,
            charge_page=charge_page,
            charge_per_page=charge_per_page,
            payment_search=payment_search,
            payment_sort=payment_sort,
            payment_direction=payment_direction,
            payment_page=payment_page,
            payment_per_page=payment_per_page,
            movement_page=movement_page,
            movement_per_page=movement_per_page,
            include_residents=False,
        )
        if selected is not None
        else None
    )
    return OrganizationResidentDetail(
        resident=resident,
        placements=placements,
        selected_placement=selected,
        apartment_finance=apartment_finance,
    )

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, exists, false, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    Announcement,
    AnnouncementAudienceScope,
    AnnouncementBuilding,
    AnnouncementRead,
    AnnouncementStatus,
    Apartment,
    ApartmentMembership,
    Building,
    OrganizationMembership,
    OrganizationMembershipRole,
    User,
    UserStatus,
)
from app.models.base import as_utc, utc_now
from app.services import EntityNotFoundError, SessionLike

ALLOWED_PAGE_SIZES = frozenset({20, 50, 100})


@dataclass(frozen=True, slots=True)
class ResidentAnnouncementItem:
    id: uuid.UUID
    title: str
    body_preview: str
    published_at: datetime
    expires_at: datetime | None
    is_read: bool


@dataclass(frozen=True, slots=True)
class ResidentAnnouncementPage:
    items: tuple[ResidentAnnouncementItem, ...]
    total: int
    page: int
    per_page: int
    pages: int


@dataclass(frozen=True, slots=True)
class ResidentAnnouncementDetail:
    id: uuid.UUID
    title: str
    body: str
    published_at: datetime
    expires_at: datetime | None


def resident_announcement_visibility_conditions(
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    now: datetime,
) -> tuple[ColumnElement[bool], ...]:
    active_building_target = exists(
        select(1)
        .select_from(AnnouncementBuilding)
        .join(
            Building,
            and_(
                Building.id == AnnouncementBuilding.building_id,
                Building.organization_id == organization_id,
                Building.is_active.is_(True),
            ),
        )
        .join(
            Apartment,
            and_(
                Apartment.building_id == Building.id,
                Apartment.organization_id == organization_id,
                Apartment.is_active.is_(True),
            ),
        )
        .join(
            ApartmentMembership,
            and_(
                ApartmentMembership.apartment_id == Apartment.id,
                ApartmentMembership.organization_id == organization_id,
                ApartmentMembership.user_id == user_id,
                ApartmentMembership.is_active.is_(True),
                ApartmentMembership.starts_at <= now,
                or_(
                    ApartmentMembership.ends_at.is_(None),
                    ApartmentMembership.ends_at >= now,
                ),
            ),
        )
        .where(
            AnnouncementBuilding.organization_id == organization_id,
            AnnouncementBuilding.announcement_id == Announcement.id,
        )
    )
    active_organization_membership = exists(
        select(1).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.role
            == OrganizationMembershipRole.ORGANIZATION_MEMBER,
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.starts_at <= now,
            or_(
                OrganizationMembership.ends_at.is_(None),
                OrganizationMembership.ends_at >= now,
            ),
        )
    )
    active_user = exists(select(1).where(User.id == user_id, User.status == UserStatus.ACTIVE))
    return (
        Announcement.organization_id == organization_id,
        Announcement.status == AnnouncementStatus.PUBLISHED,
        Announcement.published_at.is_not(None),
        Announcement.published_at <= now,
        or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
        active_user,
        active_organization_membership,
        or_(
            Announcement.audience_scope == AnnouncementAudienceScope.ORGANIZATION,
            and_(
                Announcement.audience_scope == AnnouncementAudienceScope.BUILDINGS,
                active_building_target,
            ),
        ),
    )


def list_resident_announcements(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    page: int = 1,
    per_page: int = 20,
    now: datetime | None = None,
    include_read_state: bool = True,
) -> ResidentAnnouncementPage:
    reference = as_utc(now or utc_now())
    page = max(page, 1)
    per_page = per_page if per_page in ALLOWED_PAGE_SIZES else 20
    conditions = resident_announcement_visibility_conditions(
        organization_id=organization_id, user_id=user_id, now=reference
    )
    count_value = session.execute(
        select(func.count(Announcement.id)).where(*conditions)
    ).scalar_one()
    total = int(count_value)
    pages = math.ceil(total / per_page) if total else 0
    page = min(page, pages) if pages else 1
    listing = select(
        Announcement.id,
        Announcement.title,
        Announcement.body,
        Announcement.published_at,
        Announcement.expires_at,
        (
            AnnouncementRead.id.is_not(None)
            if include_read_state
            else false()
        ).label("is_read"),
    )
    if include_read_state:
        listing = listing.outerjoin(
            AnnouncementRead,
            and_(
                AnnouncementRead.organization_id == organization_id,
                AnnouncementRead.announcement_id == Announcement.id,
                AnnouncementRead.user_id == user_id,
            ),
        )
    rows = session.execute(
        listing
        .where(*conditions)
        .order_by(Announcement.published_at.desc(), Announcement.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return ResidentAnnouncementPage(
        items=tuple(
            ResidentAnnouncementItem(
                id=row.id,
                title=row.title,
                body_preview=(row.body if len(row.body) <= 180 else f"{row.body[:177]}..."),
                published_at=as_utc(row.published_at),
                expires_at=as_utc(row.expires_at) if row.expires_at else None,
                is_read=bool(row.is_read),
            )
            for row in rows
        ),
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


def get_resident_announcement(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    announcement_id: uuid.UUID,
    now: datetime | None = None,
) -> ResidentAnnouncementDetail:
    reference = as_utc(now or utc_now())
    row = session.execute(
        select(
            Announcement.id,
            Announcement.title,
            Announcement.body,
            Announcement.published_at,
            Announcement.expires_at,
        ).where(
            *resident_announcement_visibility_conditions(
                organization_id=organization_id,
                user_id=user_id,
                now=reference,
            ),
            Announcement.id == announcement_id,
        )
    ).one_or_none()
    if row is None:
        raise EntityNotFoundError("Duyuru bulunamadı.")
    return ResidentAnnouncementDetail(
        id=row.id,
        title=row.title,
        body=row.body,
        published_at=as_utc(row.published_at),
        expires_at=as_utc(row.expires_at) if row.expires_at else None,
    )

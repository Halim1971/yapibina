from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    Announcement,
    AnnouncementAudienceScope,
    AnnouncementRead,
)
from app.models.base import as_utc, utc_now
from app.services import EntityNotFoundError, SessionLike
from app.services.resident_announcements import (
    resident_announcement_visibility_conditions,
)

ALLOWED_PAGE_SIZES = frozenset({20, 50, 100})
ALLOWED_FILTERS = frozenset({"all", "unread", "read"})


@dataclass(frozen=True, slots=True)
class ResidentNotificationItem:
    announcement_id: uuid.UUID
    title: str
    body_preview: str
    published_at: datetime
    expires_at: datetime | None
    audience_label: str
    is_read: bool
    read_at: datetime | None


@dataclass(frozen=True, slots=True)
class ResidentNotificationPage:
    items: tuple[ResidentNotificationItem, ...]
    total: int
    page: int
    per_page: int
    pages: int
    state_filter: str


@dataclass(frozen=True, slots=True)
class AnnouncementReadState:
    announcement_id: uuid.UUID
    is_read: bool
    read_at: datetime | None


def _read_join(
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ColumnElement[bool]:
    return and_(
        AnnouncementRead.organization_id == organization_id,
        AnnouncementRead.announcement_id == Announcement.id,
        AnnouncementRead.user_id == user_id,
    )


def _filter_condition(state_filter: str) -> ColumnElement[bool] | None:
    if state_filter == "unread":
        return AnnouncementRead.id.is_(None)
    if state_filter == "read":
        return AnnouncementRead.id.is_not(None)
    return None


def list_resident_notifications(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    state_filter: str = "all",
    page: int = 1,
    per_page: int = 20,
    now: datetime | None = None,
) -> ResidentNotificationPage:
    reference = as_utc(now or utc_now())
    state_filter = state_filter if state_filter in ALLOWED_FILTERS else "all"
    page = max(page, 1)
    per_page = per_page if per_page in ALLOWED_PAGE_SIZES else 20
    conditions = list(
        resident_announcement_visibility_conditions(
            organization_id=organization_id,
            user_id=user_id,
            now=reference,
        )
    )
    read_condition = _filter_condition(state_filter)
    if read_condition is not None:
        conditions.append(read_condition)
    join_condition = _read_join(organization_id=organization_id, user_id=user_id)
    total = int(
        session.execute(
            select(func.count(Announcement.id))
            .outerjoin(AnnouncementRead, join_condition)
            .where(*conditions)
        ).scalar_one()
    )
    pages = math.ceil(total / per_page) if total else 0
    page = min(page, pages) if pages else 1
    unread_first = case((AnnouncementRead.id.is_(None), 0), else_=1)
    rows = session.execute(
        select(
            Announcement.id,
            Announcement.title,
            Announcement.body,
            Announcement.published_at,
            Announcement.expires_at,
            Announcement.audience_scope,
            AnnouncementRead.read_at,
        )
        .outerjoin(AnnouncementRead, join_condition)
        .where(*conditions)
        .order_by(
            unread_first.asc(),
            Announcement.published_at.desc(),
            Announcement.id.asc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return ResidentNotificationPage(
        items=tuple(
            ResidentNotificationItem(
                announcement_id=row.id,
                title=row.title,
                body_preview=(row.body if len(row.body) <= 180 else f"{row.body[:177]}..."),
                published_at=as_utc(row.published_at),
                expires_at=as_utc(row.expires_at) if row.expires_at else None,
                audience_label=(
                    "Tüm organization"
                    if row.audience_scope is AnnouncementAudienceScope.ORGANIZATION
                    else "Bina duyurusu"
                ),
                is_read=row.read_at is not None,
                read_at=as_utc(row.read_at) if row.read_at else None,
            )
            for row in rows
        ),
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        state_filter=state_filter,
    )


def get_unread_announcement_count(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> int:
    reference = as_utc(now or utc_now())
    return int(
        session.execute(
            select(func.count(Announcement.id))
            .outerjoin(
                AnnouncementRead,
                _read_join(
                    organization_id=organization_id,
                    user_id=user_id,
                ),
            )
            .where(
                *resident_announcement_visibility_conditions(
                    organization_id=organization_id,
                    user_id=user_id,
                    now=reference,
                ),
                AnnouncementRead.id.is_(None),
            )
        ).scalar_one()
    )


def get_announcement_read_state(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    announcement_id: uuid.UUID,
    now: datetime | None = None,
) -> AnnouncementReadState:
    reference = as_utc(now or utc_now())
    row = session.execute(
        select(Announcement.id, AnnouncementRead.read_at)
        .outerjoin(
            AnnouncementRead,
            _read_join(
                organization_id=organization_id,
                user_id=user_id,
            ),
        )
        .where(
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
    return AnnouncementReadState(
        announcement_id=row.id,
        is_read=row.read_at is not None,
        read_at=as_utc(row.read_at) if row.read_at else None,
    )


def mark_announcement_read(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    announcement_id: uuid.UUID,
    read_at: datetime | None = None,
) -> AnnouncementRead:
    reference = as_utc(read_at or utc_now())
    visible_id = session.scalar(
        select(Announcement.id).where(
            *resident_announcement_visibility_conditions(
                organization_id=organization_id,
                user_id=user_id,
                now=reference,
            ),
            Announcement.id == announcement_id,
        )
    )
    if visible_id is None:
        raise EntityNotFoundError("Duyuru bulunamadı.")
    existing = session.scalar(
        select(AnnouncementRead).where(
            AnnouncementRead.organization_id == organization_id,
            AnnouncementRead.announcement_id == announcement_id,
            AnnouncementRead.user_id == user_id,
        )
    )
    if existing is not None:
        return existing
    receipt = AnnouncementRead(
        organization_id=organization_id,
        announcement_id=announcement_id,
        user_id=user_id,
        read_at=reference,
    )
    try:
        with session.begin_nested():
            session.add(receipt)
            session.flush()
    except IntegrityError:
        concurrent = session.scalar(
            select(AnnouncementRead).where(
                AnnouncementRead.organization_id == organization_id,
                AnnouncementRead.announcement_id == announcement_id,
                AnnouncementRead.user_id == user_id,
            )
        )
        if concurrent is None:
            raise
        return concurrent
    return receipt

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

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
from app.services import (
    EntityNotFoundError,
    InvalidStateTransitionError,
    ServiceValidationError,
    SessionLike,
)

TITLE_MAX_LENGTH = 160
BODY_MAX_LENGTH = 10_000
ALLOWED_PAGE_SIZES = frozenset({20, 50, 100})
ALLOWED_SORTS = frozenset({"created_at", "published_at", "title", "status"})
ALLOWED_DIRECTIONS = frozenset({"asc", "desc"})


@dataclass(frozen=True, slots=True)
class AnnouncementListItem:
    id: uuid.UUID
    title: str
    status: AnnouncementStatus
    status_label: str
    audience_scope: AnnouncementAudienceScope
    audience_label: str
    target_building_count: int
    target_buildings: tuple[str, ...]
    creator_name: str
    created_at: datetime
    published_at: datetime | None
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class AnnouncementPage:
    items: tuple[AnnouncementListItem, ...]
    total: int
    page: int
    per_page: int
    pages: int
    search: str
    status_filter: str
    audience_filter: str
    building_id: uuid.UUID | None
    sort: str
    direction: str


@dataclass(frozen=True, slots=True)
class AnnouncementDetail:
    id: uuid.UUID
    title: str
    body: str
    status: AnnouncementStatus
    status_label: str
    audience_scope: AnnouncementAudienceScope
    audience_label: str
    target_buildings: tuple[tuple[uuid.UUID, str], ...]
    creator_name: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    expires_at: datetime | None
    can_edit: bool
    can_publish: bool
    can_archive: bool
    engagement: AnnouncementEngagement


@dataclass(frozen=True, slots=True)
class AnnouncementEngagement:
    reachable_resident_count: int
    read_resident_count: int
    unread_resident_count: int
    read_rate: Decimal | None


def _clean_required(value: str, *, label: str, maximum: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ServiceValidationError(f"{label} zorunludur.")
    if len(cleaned) > maximum:
        raise ServiceValidationError(f"{label} en fazla {maximum} karakter olabilir.")
    if any(
        ord(character) < 32 and character not in "\t\n\r"
        for character in cleaned
    ):
        raise ServiceValidationError(f"{label} geçersiz kontrol karakteri içeriyor.")
    return cleaned


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ServiceValidationError("Yayın tarihleri timezone bilgisi taşımalıdır.")
    return as_utc(value)


def _validate_dates(
    published_at: datetime | None,
    expires_at: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    published = _aware(published_at)
    expires = _aware(expires_at)
    if expires is not None and published is not None and expires <= published:
        raise ServiceValidationError(
            "Son görünme tarihi yayın tarihinden sonra olmalıdır."
        )
    return published, expires


def _validate_targets(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    audience_scope: AnnouncementAudienceScope,
    building_ids: tuple[uuid.UUID, ...],
) -> tuple[Building, ...]:
    unique_ids = tuple(dict.fromkeys(building_ids))
    if audience_scope is AnnouncementAudienceScope.ORGANIZATION:
        if unique_ids:
            raise ServiceValidationError(
                "Tüm organization hedefinde bina seçilmemelidir."
            )
        return ()
    if not unique_ids:
        raise ServiceValidationError("En az bir aktif bina seçmelisiniz.")
    buildings = tuple(
        session.scalars(
            select(Building)
            .where(
                Building.organization_id == organization_id,
                Building.id.in_(unique_ids),
                Building.is_active.is_(True),
            )
            .order_by(Building.name, Building.id)
        )
    )
    if len(buildings) != len(unique_ids):
        raise ServiceValidationError("Seçilen binalardan biri kullanılamıyor.")
    return buildings


def _status_label(announcement: Announcement, now: datetime) -> str:
    if announcement.status is AnnouncementStatus.DRAFT:
        return "Taslak"
    if announcement.status is AnnouncementStatus.ARCHIVED:
        return "Arşivlendi"
    if announcement.published_at is not None and as_utc(announcement.published_at) > now:
        return "Planlandı"
    if announcement.expires_at is not None and as_utc(announcement.expires_at) <= now:
        return "Süresi Doldu"
    return "Yayında"


def _audience_label(announcement: Announcement) -> str:
    if announcement.audience_scope is AnnouncementAudienceScope.ORGANIZATION:
        return "Tüm organization"
    count = len(announcement.building_targets)
    return f"{count} bina"


def _creator_name(user: User) -> str:
    name = f"{user.first_name} {user.last_name}".strip()
    return name or user.email


def _load_scoped(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    announcement_id: uuid.UUID,
) -> Announcement:
    announcement = session.scalar(
        select(Announcement)
        .options(
            selectinload(Announcement.creator),
            selectinload(Announcement.building_targets).selectinload(
                AnnouncementBuilding.building
            ),
        )
        .where(
            Announcement.organization_id == organization_id,
            Announcement.id == announcement_id,
        )
    )
    if announcement is None:
        raise EntityNotFoundError("Duyuru bulunamadı.")
    return announcement


def _announcement_engagement(
    session: SessionLike,
    *,
    announcement: Announcement,
    now: datetime,
) -> AnnouncementEngagement:
    active_membership_conditions = (
        OrganizationMembership.organization_id == announcement.organization_id,
        OrganizationMembership.role
        == OrganizationMembershipRole.ORGANIZATION_MEMBER,
        OrganizationMembership.is_active.is_(True),
        OrganizationMembership.starts_at <= now,
        or_(
            OrganizationMembership.ends_at.is_(None),
            OrganizationMembership.ends_at >= now,
        ),
        User.status == UserStatus.ACTIVE,
    )
    if (
        announcement.audience_scope
        is AnnouncementAudienceScope.ORGANIZATION
    ):
        reachable_statement = (
            select(func.count(func.distinct(User.id)))
            .select_from(User)
            .join(
                OrganizationMembership,
                OrganizationMembership.user_id == User.id,
            )
            .where(*active_membership_conditions)
        )
    else:
        reachable_statement = (
            select(func.count(func.distinct(User.id)))
            .select_from(User)
            .join(
                OrganizationMembership,
                OrganizationMembership.user_id == User.id,
            )
            .join(
                ApartmentMembership,
                and_(
                    ApartmentMembership.user_id == User.id,
                    ApartmentMembership.organization_id
                    == announcement.organization_id,
                    ApartmentMembership.is_active.is_(True),
                    ApartmentMembership.starts_at <= now,
                    or_(
                        ApartmentMembership.ends_at.is_(None),
                        ApartmentMembership.ends_at >= now,
                    ),
                ),
            )
            .join(
                Apartment,
                and_(
                    Apartment.id == ApartmentMembership.apartment_id,
                    Apartment.organization_id == announcement.organization_id,
                    Apartment.is_active.is_(True),
                ),
            )
            .join(
                Building,
                and_(
                    Building.id == Apartment.building_id,
                    Building.organization_id == announcement.organization_id,
                    Building.is_active.is_(True),
                ),
            )
            .join(
                AnnouncementBuilding,
                and_(
                    AnnouncementBuilding.organization_id
                    == announcement.organization_id,
                    AnnouncementBuilding.announcement_id == announcement.id,
                    AnnouncementBuilding.building_id == Building.id,
                ),
            )
            .where(*active_membership_conditions)
        )
    read_statement = select(
        func.count(func.distinct(AnnouncementRead.user_id))
    ).where(
        AnnouncementRead.organization_id == announcement.organization_id,
        AnnouncementRead.announcement_id == announcement.id,
    )
    reachable = int(session.scalar(reachable_statement) or 0)
    read = int(session.scalar(read_statement) or 0)
    unread = max(reachable - read, 0)
    rate = (
        min(
            (Decimal(read) * Decimal("100")) / Decimal(reachable),
            Decimal("100"),
        ).quantize(Decimal("0.1"))
        if reachable
        else None
    )
    return AnnouncementEngagement(
        reachable_resident_count=reachable,
        read_resident_count=read,
        unread_resident_count=unread,
        read_rate=rate,
    )


def create_announcement(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    title: str,
    body: str,
    audience_scope: AnnouncementAudienceScope,
    building_ids: tuple[uuid.UUID, ...] = (),
    publish_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> Announcement:
    creator_exists = session.scalar(
        select(func.count(User.id))
        .join(
            OrganizationMembership,
            OrganizationMembership.user_id == User.id,
        )
        .where(
            User.id == created_by_user_id,
            User.status == UserStatus.ACTIVE,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.role
            == OrganizationMembershipRole.ORGANIZATION_ADMIN,
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.starts_at <= utc_now(),
            or_(
                OrganizationMembership.ends_at.is_(None),
                OrganizationMembership.ends_at >= utc_now(),
            ),
        )
    )
    if not creator_exists:
        raise ServiceValidationError(
            "Duyuruyu oluşturan aktif organization admin bulunamadı."
        )
    buildings = _validate_targets(
        session,
        organization_id=organization_id,
        audience_scope=audience_scope,
        building_ids=building_ids,
    )
    published, expires = _validate_dates(publish_at, expires_at)
    announcement = Announcement(
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        title=_clean_required(title, label="Başlık", maximum=TITLE_MAX_LENGTH),
        body=_clean_required(body, label="Duyuru metni", maximum=BODY_MAX_LENGTH),
        status=(
            AnnouncementStatus.PUBLISHED
            if published is not None
            else AnnouncementStatus.DRAFT
        ),
        audience_scope=audience_scope,
        published_at=published,
        expires_at=expires,
    )
    announcement.building_targets = [
        AnnouncementBuilding(
            organization_id=organization_id,
            building_id=building.id,
        )
        for building in buildings
    ]
    session.add(announcement)
    session.flush()
    return announcement


def update_draft_announcement(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    announcement_id: uuid.UUID,
    title: str,
    body: str,
    audience_scope: AnnouncementAudienceScope,
    building_ids: tuple[uuid.UUID, ...] = (),
    publish_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> Announcement:
    announcement = _load_scoped(
        session,
        organization_id=organization_id,
        announcement_id=announcement_id,
    )
    scheduled = (
        announcement.status is AnnouncementStatus.PUBLISHED
        and announcement.published_at is not None
        and as_utc(announcement.published_at) > utc_now()
    )
    if announcement.status is not AnnouncementStatus.DRAFT and not scheduled:
        raise InvalidStateTransitionError("Yayınlanmış duyuru düzenlenemez.")
    buildings = _validate_targets(
        session,
        organization_id=organization_id,
        audience_scope=audience_scope,
        building_ids=building_ids,
    )
    published, expires = _validate_dates(publish_at, expires_at)
    if scheduled and published is None:
        raise InvalidStateTransitionError(
            "Planlanmış duyuru yeniden taslağa alınamaz."
        )
    announcement.title = _clean_required(
        title, label="Başlık", maximum=TITLE_MAX_LENGTH
    )
    announcement.body = _clean_required(
        body, label="Duyuru metni", maximum=BODY_MAX_LENGTH
    )
    announcement.audience_scope = audience_scope
    announcement.status = (
        AnnouncementStatus.PUBLISHED
        if scheduled or published is not None
        else AnnouncementStatus.DRAFT
    )
    announcement.published_at = published
    announcement.expires_at = expires
    announcement.building_targets.clear()
    announcement.building_targets.extend(
        AnnouncementBuilding(
            organization_id=organization_id,
            building_id=building.id,
        )
        for building in buildings
    )
    session.flush()
    return announcement


def publish_announcement(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    announcement_id: uuid.UUID,
    published_at: datetime | None = None,
) -> Announcement:
    announcement = _load_scoped(
        session,
        organization_id=organization_id,
        announcement_id=announcement_id,
    )
    if announcement.status is AnnouncementStatus.PUBLISHED:
        return announcement
    if announcement.status is not AnnouncementStatus.DRAFT:
        raise InvalidStateTransitionError("Arşivlenmiş duyuru yayınlanamaz.")
    announcement.status = AnnouncementStatus.PUBLISHED
    announcement.published_at = _aware(published_at) or utc_now()
    if (
        announcement.expires_at is not None
        and as_utc(announcement.expires_at) <= as_utc(announcement.published_at)
    ):
        raise ServiceValidationError(
            "Son görünme tarihi yayın tarihinden sonra olmalıdır."
        )
    session.flush()
    return announcement


def archive_announcement(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    announcement_id: uuid.UUID,
) -> Announcement:
    announcement = _load_scoped(
        session,
        organization_id=organization_id,
        announcement_id=announcement_id,
    )
    if announcement.status is AnnouncementStatus.ARCHIVED:
        return announcement
    announcement.status = AnnouncementStatus.ARCHIVED
    session.flush()
    return announcement


def get_organization_announcement(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    announcement_id: uuid.UUID,
    now: datetime | None = None,
) -> AnnouncementDetail:
    reference = as_utc(now or utc_now())
    announcement = _load_scoped(
        session,
        organization_id=organization_id,
        announcement_id=announcement_id,
    )
    scheduled = (
        announcement.status is AnnouncementStatus.PUBLISHED
        and announcement.published_at is not None
        and as_utc(announcement.published_at) > reference
    )
    engagement = _announcement_engagement(
        session,
        announcement=announcement,
        now=reference,
    )
    return AnnouncementDetail(
        id=announcement.id,
        title=announcement.title,
        body=announcement.body,
        status=announcement.status,
        status_label=_status_label(announcement, reference),
        audience_scope=announcement.audience_scope,
        audience_label=_audience_label(announcement),
        target_buildings=tuple(
            (target.building.id, target.building.name)
            for target in sorted(
                announcement.building_targets,
                key=lambda target: (target.building.name.casefold(), target.building.id),
            )
        ),
        creator_name=_creator_name(announcement.creator),
        created_at=as_utc(announcement.created_at),
        updated_at=as_utc(announcement.updated_at),
        published_at=(
            as_utc(announcement.published_at)
            if announcement.published_at
            else None
        ),
        expires_at=(
            as_utc(announcement.expires_at) if announcement.expires_at else None
        ),
        can_edit=announcement.status is AnnouncementStatus.DRAFT or scheduled,
        can_publish=announcement.status is AnnouncementStatus.DRAFT,
        can_archive=announcement.status is not AnnouncementStatus.ARCHIVED,
        engagement=engagement,
    )


def list_organization_announcements(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    search: str = "",
    status_filter: str = "",
    audience_filter: str = "",
    building_id: uuid.UUID | None = None,
    sort: str = "created_at",
    direction: str = "desc",
    page: int = 1,
    per_page: int = 20,
    now: datetime | None = None,
) -> AnnouncementPage:
    search = search.strip()
    status_filter = (
        status_filter
        if status_filter in {item.value for item in AnnouncementStatus}
        else ""
    )
    audience_filter = (
        audience_filter
        if audience_filter in {item.value for item in AnnouncementAudienceScope}
        else ""
    )
    sort = sort if sort in ALLOWED_SORTS else "created_at"
    direction = direction if direction in ALLOWED_DIRECTIONS else "desc"
    page = max(page, 1)
    per_page = per_page if per_page in ALLOWED_PAGE_SIZES else 20
    conditions = [Announcement.organization_id == organization_id]
    if search:
        pattern = f"%{search}%"
        conditions.append(or_(Announcement.title.ilike(pattern), Announcement.body.ilike(pattern)))
    if status_filter:
        conditions.append(Announcement.status == AnnouncementStatus(status_filter))
    if audience_filter:
        conditions.append(
            Announcement.audience_scope == AnnouncementAudienceScope(audience_filter)
        )
    if building_id is not None:
        conditions.append(
            Announcement.building_targets.any(
                and_(
                    AnnouncementBuilding.organization_id == organization_id,
                    AnnouncementBuilding.building_id == building_id,
                )
            )
        )
    total = int(
        session.scalar(select(func.count(Announcement.id)).where(*conditions)) or 0
    )
    pages = math.ceil(total / per_page) if total else 0
    page = min(page, pages) if pages else 1
    sort_columns = {
        "created_at": Announcement.created_at,
        "published_at": Announcement.published_at,
        "title": Announcement.title,
        "status": Announcement.status,
    }
    primary = sort_columns[sort]
    ordering = primary.desc() if direction == "desc" else primary.asc()
    announcements = tuple(
        session.scalars(
            select(Announcement)
            .options(
                selectinload(Announcement.creator),
                selectinload(Announcement.building_targets).selectinload(
                    AnnouncementBuilding.building
                ),
            )
            .where(*conditions)
            .order_by(ordering, Announcement.id.asc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    )
    reference = as_utc(now or utc_now())
    return AnnouncementPage(
        items=tuple(
            AnnouncementListItem(
                id=item.id,
                title=item.title,
                status=item.status,
                status_label=_status_label(item, reference),
                audience_scope=item.audience_scope,
                audience_label=_audience_label(item),
                target_building_count=len(item.building_targets),
                target_buildings=tuple(
                    target.building.name
                    for target in sorted(
                        item.building_targets,
                        key=lambda target: (
                            target.building.name.casefold(),
                            target.building.id,
                        ),
                    )
                ),
                creator_name=_creator_name(item.creator),
                created_at=as_utc(item.created_at),
                published_at=(
                    as_utc(item.published_at) if item.published_at else None
                ),
                expires_at=as_utc(item.expires_at) if item.expires_at else None,
            )
            for item in announcements
        ),
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        search=search,
        status_filter=status_filter,
        audience_filter=audience_filter,
        building_id=building_id,
        sort=sort,
        direction=direction,
    )

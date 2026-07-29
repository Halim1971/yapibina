from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Numeric, and_, case, cast, func, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.models import (
    Apartment,
    ApartmentMembership,
    Building,
    Charge,
    ChargeStatus,
    OrganizationMembership,
    Payment,
    PaymentAllocation,
    PaymentStatus,
    User,
    UserStatus,
)
from app.services import SessionLike
from app.services.finance_metrics import (
    local_today,
    money_decimal,
    month_range,
)

ALLOWED_SORTS = frozenset({"name", "apartments", "debt", "payments"})
ALLOWED_DIRECTIONS = frozenset({"asc", "desc"})
ALLOWED_PAGE_SIZES = frozenset({20, 50, 100})
DEFAULT_PAGE_SIZE = 20


@dataclass(frozen=True, slots=True)
class BuildingListItem:
    id: uuid.UUID
    name: str
    address: str
    apartment_count: int
    active_resident_count: int
    outstanding_debt: Decimal
    current_month_payments: Decimal
    is_active: bool


@dataclass(frozen=True, slots=True)
class BuildingListPage:
    items: tuple[BuildingListItem, ...]
    total: int
    page: int
    per_page: int
    pages: int
    search: str
    sort: str
    direction: str

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


def _normalized_options(
    *,
    search: str,
    sort: str,
    direction: str,
    page: int,
    per_page: int,
) -> tuple[str, str, str, int, int]:
    return (
        search.strip(),
        sort if sort in ALLOWED_SORTS else "name",
        direction if direction in ALLOWED_DIRECTIONS else "asc",
        max(page, 1),
        per_page if per_page in ALLOWED_PAGE_SIZES else DEFAULT_PAGE_SIZE,
    )


def _search_filter(search: str) -> ColumnElement[bool] | None:
    if not search:
        return None
    pattern = f"%{search}%"
    return or_(
        Building.name.ilike(pattern),
        Building.address_line.ilike(pattern),
        Building.district.ilike(pattern),
        Building.city.ilike(pattern),
    )


def _apartment_counts(organization_id: uuid.UUID) -> Subquery:
    return (
        select(
            Apartment.building_id.label("building_id"),
            func.count(Apartment.id).label("apartment_count"),
        )
        .where(Apartment.organization_id == organization_id)
        .group_by(Apartment.building_id)
        .subquery()
    )


def _resident_counts(
    organization_id: uuid.UUID,
    now: datetime,
) -> Subquery:
    return (
        select(
            Apartment.building_id.label("building_id"),
            func.count(func.distinct(ApartmentMembership.user_id)).label(
                "resident_count"
            ),
        )
        .join(
            ApartmentMembership,
            and_(
                ApartmentMembership.apartment_id == Apartment.id,
                ApartmentMembership.organization_id == organization_id,
            ),
        )
        .join(User, User.id == ApartmentMembership.user_id)
        .join(
            OrganizationMembership,
            and_(
                OrganizationMembership.user_id == User.id,
                OrganizationMembership.organization_id == organization_id,
            ),
        )
        .join(Building, Building.id == Apartment.building_id)
        .where(
            Apartment.organization_id == organization_id,
            Apartment.is_active.is_(True),
            Building.organization_id == organization_id,
            Building.is_active.is_(True),
            User.status == UserStatus.ACTIVE,
            ApartmentMembership.is_active.is_(True),
            ApartmentMembership.starts_at <= now,
            or_(
                ApartmentMembership.ends_at.is_(None),
                ApartmentMembership.ends_at >= now,
            ),
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.starts_at <= now,
            or_(
                OrganizationMembership.ends_at.is_(None),
                OrganizationMembership.ends_at >= now,
            ),
        )
        .group_by(Apartment.building_id)
        .subquery()
    )


def _charge_totals(organization_id: uuid.UUID) -> Subquery:
    return (
        select(
            Charge.building_id.label("building_id"),
            func.sum(Charge.original_amount).label("charge_total"),
        )
        .where(
            Charge.organization_id == organization_id,
            Charge.status == ChargeStatus.POSTED,
        )
        .group_by(Charge.building_id)
        .subquery()
    )


def _allocation_totals(organization_id: uuid.UUID) -> Subquery:
    return (
        select(
            Charge.building_id.label("building_id"),
            func.sum(PaymentAllocation.amount).label("allocation_total"),
        )
        .join(
            Charge,
            and_(
                Charge.id == PaymentAllocation.charge_id,
                Charge.organization_id == organization_id,
            ),
        )
        .join(
            Payment,
            and_(
                Payment.id == PaymentAllocation.payment_id,
                Payment.organization_id == organization_id,
            ),
        )
        .where(
            PaymentAllocation.organization_id == organization_id,
            Charge.status == ChargeStatus.POSTED,
            Payment.status == PaymentStatus.POSTED,
        )
        .group_by(Charge.building_id)
        .subquery()
    )


def _monthly_payment_totals(
    organization_id: uuid.UUID,
    start: date,
    end: date,
) -> Subquery:
    return (
        select(
            Payment.building_id.label("building_id"),
            func.sum(Payment.amount).label("payment_total"),
        )
        .where(
            Payment.organization_id == organization_id,
            Payment.status == PaymentStatus.POSTED,
            Payment.payment_date >= start,
            Payment.payment_date < end,
        )
        .group_by(Payment.building_id)
        .subquery()
    )


def _address(row: object) -> str:
    parts = [
        getattr(row, "address_line", None),
        getattr(row, "district", None),
        getattr(row, "city", None),
    ]
    return ", ".join(str(part) for part in parts if part) or "Adres belirtilmedi"


def list_organization_buildings(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    timezone_name: str,
    search: str = "",
    sort: str = "name",
    direction: str = "asc",
    page: int = 1,
    per_page: int = DEFAULT_PAGE_SIZE,
    reference_date: date | None = None,
) -> BuildingListPage:
    search, sort, direction, page, per_page = _normalized_options(
        search=search,
        sort=sort,
        direction=direction,
        page=page,
        per_page=per_page,
    )
    today = reference_date or local_today(timezone_name)
    month_start, month_end = month_range(today)
    now = datetime.now(timezone.utc)
    apartments = _apartment_counts(organization_id)
    residents = _resident_counts(organization_id, now)
    charges = _charge_totals(organization_id)
    allocations = _allocation_totals(organization_id)
    payments = _monthly_payment_totals(
        organization_id,
        month_start,
        month_end,
    )
    zero_money = cast(0, Numeric(14, 2))
    charge_total = func.coalesce(charges.c.charge_total, zero_money)
    allocation_total = func.coalesce(
        allocations.c.allocation_total,
        zero_money,
    )
    debt_difference = charge_total - allocation_total
    outstanding_debt = case(
        (debt_difference < 0, zero_money),
        else_=debt_difference,
    ).label("outstanding_debt")
    apartment_count = func.coalesce(
        apartments.c.apartment_count,
        0,
    ).label("apartment_count")
    resident_count = func.coalesce(
        residents.c.resident_count,
        0,
    ).label("resident_count")
    payment_total = func.coalesce(
        payments.c.payment_total,
        zero_money,
    ).label("payment_total")
    search_condition = _search_filter(search)
    count_statement = select(func.count(Building.id)).where(
        Building.organization_id == organization_id
    )
    if search_condition is not None:
        count_statement = count_statement.where(search_condition)
    total = int(session.scalar(count_statement) or 0)
    pages = math.ceil(total / per_page) if total else 0
    page = min(page, pages) if pages else 1

    sort_expressions = {
        "name": Building.name,
        "apartments": apartment_count,
        "debt": outstanding_debt,
        "payments": payment_total,
    }
    primary_sort = sort_expressions[sort]
    ordering = primary_sort.desc() if direction == "desc" else primary_sort.asc()
    statement = (
        select(
            Building.id,
            Building.name,
            Building.address_line,
            Building.district,
            Building.city,
            Building.is_active,
            apartment_count,
            resident_count,
            outstanding_debt,
            payment_total,
        )
        .outerjoin(apartments, apartments.c.building_id == Building.id)
        .outerjoin(residents, residents.c.building_id == Building.id)
        .outerjoin(charges, charges.c.building_id == Building.id)
        .outerjoin(allocations, allocations.c.building_id == Building.id)
        .outerjoin(payments, payments.c.building_id == Building.id)
        .where(Building.organization_id == organization_id)
    )
    if search_condition is not None:
        statement = statement.where(search_condition)
    statement = statement.order_by(
        ordering,
        Building.name.asc(),
        Building.id.asc(),
    ).offset((page - 1) * per_page).limit(per_page)
    rows = session.execute(statement).all()
    return BuildingListPage(
        items=tuple(
            BuildingListItem(
                id=row.id,
                name=row.name,
                address=_address(row),
                apartment_count=int(row.apartment_count),
                active_resident_count=int(row.resident_count),
                outstanding_debt=money_decimal(row.outstanding_debt),
                current_month_payments=money_decimal(row.payment_total),
                is_active=bool(row.is_active),
            )
            for row in rows
        ),
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        search=search,
        sort=sort,
        direction=direction,
    )

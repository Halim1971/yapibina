from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric, and_, case, cast, exists, func, or_, select
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
from app.services import ServiceValidationError, SessionLike
from app.services.finance_metrics import (
    MONEY_ZERO,
    local_today,
    money_decimal,
    month_range,
    period_charge_filter,
)

ALLOWED_SORTS = frozenset(
    {"apartment", "residents", "debt", "charges", "payments", "last_payment"}
)
ALLOWED_DIRECTIONS = frozenset({"asc", "desc"})
ALLOWED_PAGE_SIZES = frozenset({20, 50, 100})
DEFAULT_PAGE_SIZE = 20


@dataclass(frozen=True, slots=True)
class BuildingDetailSummary:
    id: uuid.UUID
    name: str
    address: str
    is_active: bool
    apartment_count: int
    active_resident_count: int
    outstanding_debt: Decimal
    current_month_charges: Decimal
    current_month_payments: Decimal
    collection_rate: Decimal | None
    last_financial_movement_date: date | None
    period_label: str


@dataclass(frozen=True, slots=True)
class ApartmentDetailRow:
    id: uuid.UUID
    label: str
    location: str
    resident_summary: str
    active_resident_count: int
    outstanding_debt: Decimal
    current_month_charges: Decimal
    current_month_payments: Decimal
    last_payment_date: date | None
    last_payment_amount: Decimal | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class ApartmentDetailPage:
    items: tuple[ApartmentDetailRow, ...]
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


@dataclass(frozen=True, slots=True)
class BuildingFinancialMovement:
    id: uuid.UUID
    movement_date: date
    apartment_label: str
    description: str
    amount: Decimal
    kind: str


@dataclass(frozen=True, slots=True)
class OrganizationBuildingDetail:
    building: BuildingDetailSummary
    apartments: ApartmentDetailPage
    movements: tuple[BuildingFinancialMovement, ...]


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
        sort if sort in ALLOWED_SORTS else "apartment",
        direction if direction in ALLOWED_DIRECTIONS else "asc",
        max(page, 1),
        per_page if per_page in ALLOWED_PAGE_SIZES else DEFAULT_PAGE_SIZE,
    )


def _address(building: Building) -> str:
    parts = [
        building.address_line,
        building.district,
        building.city,
        building.postal_code,
    ]
    return ", ".join(part for part in parts if part) or "Adres belirtilmedi"


def _active_residents(
    organization_id: uuid.UUID,
    now: datetime,
) -> Subquery:
    return (
        select(
            ApartmentMembership.apartment_id.label("apartment_id"),
            func.count(func.distinct(ApartmentMembership.user_id)).label(
                "resident_count"
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
        .where(
            ApartmentMembership.organization_id == organization_id,
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
        .group_by(ApartmentMembership.apartment_id)
        .subquery()
    )


def _charge_totals(organization_id: uuid.UUID) -> Subquery:
    return (
        select(
            Charge.apartment_id.label("apartment_id"),
            func.sum(Charge.original_amount).label("charge_total"),
        )
        .where(
            Charge.organization_id == organization_id,
            Charge.status == ChargeStatus.POSTED,
        )
        .group_by(Charge.apartment_id)
        .subquery()
    )


def _allocation_totals(organization_id: uuid.UUID) -> Subquery:
    return (
        select(
            Charge.apartment_id.label("apartment_id"),
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
        .group_by(Charge.apartment_id)
        .subquery()
    )


def _monthly_charge_totals(
    organization_id: uuid.UUID,
    start: date,
    end: date,
) -> Subquery:
    return (
        select(
            Charge.apartment_id.label("apartment_id"),
            func.sum(Charge.original_amount).label("charge_total"),
        )
        .where(
            Charge.organization_id == organization_id,
            Charge.status == ChargeStatus.POSTED,
            period_charge_filter(start, end),
        )
        .group_by(Charge.apartment_id)
        .subquery()
    )


def _monthly_payment_totals(
    organization_id: uuid.UUID,
    start: date,
    end: date,
) -> Subquery:
    return (
        select(
            Payment.apartment_id.label("apartment_id"),
            func.sum(Payment.amount).label("payment_total"),
        )
        .where(
            Payment.organization_id == organization_id,
            Payment.status == PaymentStatus.POSTED,
            Payment.payment_date >= start,
            Payment.payment_date < end,
        )
        .group_by(Payment.apartment_id)
        .subquery()
    )


def _latest_payments(organization_id: uuid.UUID) -> Subquery:
    ranked = (
        select(
            Payment.apartment_id.label("apartment_id"),
            Payment.payment_date.label("payment_date"),
            Payment.amount.label("amount"),
            func.row_number()
            .over(
                partition_by=Payment.apartment_id,
                order_by=(
                    Payment.payment_date.desc(),
                    Payment.created_at.desc(),
                    Payment.id.desc(),
                ),
            )
            .label("position"),
        )
        .where(
            Payment.organization_id == organization_id,
            Payment.status == PaymentStatus.POSTED,
        )
        .subquery()
    )
    return (
        select(
            ranked.c.apartment_id,
            ranked.c.payment_date,
            ranked.c.amount,
        )
        .where(ranked.c.position == 1)
        .subquery()
    )


def _active_resident_exists(
    *,
    organization_id: uuid.UUID,
    now: datetime,
    search_pattern: str,
) -> ColumnElement[bool]:
    return exists(
        select(ApartmentMembership.id)
        .join(User, User.id == ApartmentMembership.user_id)
        .join(
            OrganizationMembership,
            and_(
                OrganizationMembership.user_id == User.id,
                OrganizationMembership.organization_id == organization_id,
            ),
        )
        .where(
            ApartmentMembership.organization_id == organization_id,
            ApartmentMembership.apartment_id == Apartment.id,
            ApartmentMembership.is_active.is_(True),
            ApartmentMembership.starts_at <= now,
            or_(
                ApartmentMembership.ends_at.is_(None),
                ApartmentMembership.ends_at >= now,
            ),
            User.status == UserStatus.ACTIVE,
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.starts_at <= now,
            or_(
                OrganizationMembership.ends_at.is_(None),
                OrganizationMembership.ends_at >= now,
            ),
            or_(
                User.first_name.ilike(search_pattern),
                User.last_name.ilike(search_pattern),
            ),
        )
    )


def _resident_names(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_ids: tuple[uuid.UUID, ...],
    now: datetime,
) -> dict[uuid.UUID, list[str]]:
    if not apartment_ids:
        return {}
    rows = session.execute(
        select(
            ApartmentMembership.apartment_id,
            User.id,
            User.first_name,
            User.last_name,
            User.email,
        )
        .join(User, User.id == ApartmentMembership.user_id)
        .join(
            OrganizationMembership,
            and_(
                OrganizationMembership.user_id == User.id,
                OrganizationMembership.organization_id == organization_id,
            ),
        )
        .where(
            ApartmentMembership.organization_id == organization_id,
            ApartmentMembership.apartment_id.in_(apartment_ids),
            ApartmentMembership.is_active.is_(True),
            ApartmentMembership.starts_at <= now,
            or_(
                ApartmentMembership.ends_at.is_(None),
                ApartmentMembership.ends_at >= now,
            ),
            User.status == UserStatus.ACTIVE,
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.starts_at <= now,
            or_(
                OrganizationMembership.ends_at.is_(None),
                OrganizationMembership.ends_at >= now,
            ),
        )
        .distinct()
        .order_by(
            ApartmentMembership.apartment_id,
            User.first_name,
            User.last_name,
            User.id,
        )
    ).all()
    names: dict[uuid.UUID, list[str]] = {}
    for row in rows:
        display_name = f"{row.first_name} {row.last_name}".strip() or row.email
        names.setdefault(row.apartment_id, []).append(display_name)
    return names


def _resident_summary(names: list[str]) -> str:
    if not names:
        return "İkamet eden yok"
    if len(names) == 1:
        return names[0]
    return f"{names[0]} ve {len(names) - 1} kişi"


def _recent_movements(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
) -> tuple[BuildingFinancialMovement, ...]:
    charges = session.execute(
        select(
            Charge.id,
            Charge.due_date,
            Apartment.unit_code,
            Apartment.number,
            Charge.title,
            Charge.original_amount,
        )
        .join(
            Apartment,
            and_(
                Apartment.id == Charge.apartment_id,
                Apartment.organization_id == organization_id,
            ),
        )
        .where(
            Charge.organization_id == organization_id,
            Charge.building_id == building_id,
            Charge.status == ChargeStatus.POSTED,
        )
        .order_by(Charge.due_date.desc(), Charge.created_at.desc(), Charge.id.desc())
        .limit(10)
    ).all()
    payments = session.execute(
        select(
            Payment.id,
            Payment.payment_date,
            Apartment.unit_code,
            Apartment.number,
            Payment.description,
            Payment.reference,
            Payment.amount,
        )
        .join(
            Apartment,
            and_(
                Apartment.id == Payment.apartment_id,
                Apartment.organization_id == organization_id,
            ),
        )
        .where(
            Payment.organization_id == organization_id,
            Payment.building_id == building_id,
            Payment.status == PaymentStatus.POSTED,
        )
        .order_by(
            Payment.payment_date.desc(),
            Payment.created_at.desc(),
            Payment.id.desc(),
        )
        .limit(10)
    ).all()
    movements = [
        BuildingFinancialMovement(
            id=row.id,
            movement_date=row.due_date,
            apartment_label=row.unit_code or row.number,
            description=row.title,
            amount=money_decimal(row.original_amount),
            kind="Borç",
        )
        for row in charges
    ]
    movements.extend(
        BuildingFinancialMovement(
            id=row.id,
            movement_date=row.payment_date,
            apartment_label=row.unit_code or row.number,
            description=row.description or row.reference or "Ödeme",
            amount=money_decimal(row.amount),
            kind="Ödeme",
        )
        for row in payments
    )
    return tuple(
        sorted(
            movements,
            key=lambda item: (item.movement_date, item.kind, str(item.id)),
            reverse=True,
        )[:10]
    )


def get_organization_building_detail(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    timezone_name: str,
    search: str = "",
    sort: str = "apartment",
    direction: str = "asc",
    page: int = 1,
    per_page: int = DEFAULT_PAGE_SIZE,
    reference_date: date | None = None,
) -> OrganizationBuildingDetail:
    building = session.scalar(
        select(Building).where(
            Building.id == building_id,
            Building.organization_id == organization_id,
        )
    )
    if building is None:
        raise ServiceValidationError("Bina bulunamadı.")

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
    residents = _active_residents(organization_id, now)
    charges = _charge_totals(organization_id)
    allocations = _allocation_totals(organization_id)
    monthly_charges = _monthly_charge_totals(
        organization_id,
        month_start,
        month_end,
    )
    monthly_payments = _monthly_payment_totals(
        organization_id,
        month_start,
        month_end,
    )
    latest_payments = _latest_payments(organization_id)
    zero_money = cast(0, Numeric(14, 2))
    charge_total = func.coalesce(charges.c.charge_total, zero_money)
    allocation_total = func.coalesce(allocations.c.allocation_total, zero_money)
    debt_difference = charge_total - allocation_total
    outstanding_debt = case(
        (debt_difference < 0, zero_money),
        else_=debt_difference,
    ).label("outstanding_debt")
    resident_count = func.coalesce(
        residents.c.resident_count,
        0,
    ).label("resident_count")
    current_charges = func.coalesce(
        monthly_charges.c.charge_total,
        zero_money,
    ).label("current_charges")
    current_payments = func.coalesce(
        monthly_payments.c.payment_total,
        zero_money,
    ).label("current_payments")

    search_condition: ColumnElement[bool] | None = None
    if search:
        pattern = f"%{search}%"
        search_condition = or_(
            Apartment.number.ilike(pattern),
            Apartment.unit_code.ilike(pattern),
            _active_resident_exists(
                organization_id=organization_id,
                now=now,
                search_pattern=pattern,
            ),
        )
    base_conditions = (
        Apartment.organization_id == organization_id,
        Apartment.building_id == building_id,
    )
    count_statement = select(func.count(Apartment.id)).where(*base_conditions)
    if search_condition is not None:
        count_statement = count_statement.where(search_condition)
    total = int(session.scalar(count_statement) or 0)
    pages = math.ceil(total / per_page) if total else 0
    page = min(page, pages) if pages else 1

    apartment_label = func.coalesce(Apartment.unit_code, Apartment.number)
    sort_expressions = {
        "apartment": apartment_label,
        "residents": resident_count,
        "debt": outstanding_debt,
        "charges": current_charges,
        "payments": current_payments,
        "last_payment": latest_payments.c.payment_date,
    }
    primary_sort = sort_expressions[sort]
    ordering: tuple[Any, ...]
    if sort == "apartment":
        ordering = (
            (func.length(apartment_label).desc(), apartment_label.desc())
            if direction == "desc"
            else (func.length(apartment_label).asc(), apartment_label.asc())
        )
    else:
        ordering = (
            (primary_sort.desc(),)
            if direction == "desc"
            else (primary_sort.asc(),)
        )
    statement = (
        select(
            Apartment.id,
            Apartment.number,
            Apartment.unit_code,
            Apartment.block,
            Apartment.floor,
            Apartment.is_active,
            resident_count,
            outstanding_debt,
            current_charges,
            current_payments,
            latest_payments.c.payment_date.label("last_payment_date"),
            latest_payments.c.amount.label("last_payment_amount"),
        )
        .outerjoin(residents, residents.c.apartment_id == Apartment.id)
        .outerjoin(charges, charges.c.apartment_id == Apartment.id)
        .outerjoin(allocations, allocations.c.apartment_id == Apartment.id)
        .outerjoin(monthly_charges, monthly_charges.c.apartment_id == Apartment.id)
        .outerjoin(monthly_payments, monthly_payments.c.apartment_id == Apartment.id)
        .outerjoin(latest_payments, latest_payments.c.apartment_id == Apartment.id)
        .where(*base_conditions)
    )
    if search_condition is not None:
        statement = statement.where(search_condition)
    rows = session.execute(
        statement.order_by(
            *ordering,
            apartment_label.asc(),
            Apartment.id.asc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    apartment_ids = tuple(row.id for row in rows)
    names = _resident_names(
        session,
        organization_id=organization_id,
        apartment_ids=apartment_ids,
        now=now,
    )
    apartment_items = tuple(
        ApartmentDetailRow(
            id=row.id,
            label=row.unit_code or row.number,
            location=" · ".join(
                part
                for part in (
                    f"Blok {row.block}" if row.block else None,
                    f"Kat {row.floor}" if row.floor else None,
                    f"Bağımsız Bölüm {row.number}",
                )
                if part
            ),
            resident_summary=_resident_summary(names.get(row.id, [])),
            active_resident_count=int(row.resident_count),
            outstanding_debt=money_decimal(row.outstanding_debt),
            current_month_charges=money_decimal(row.current_charges),
            current_month_payments=money_decimal(row.current_payments),
            last_payment_date=row.last_payment_date,
            last_payment_amount=(
                money_decimal(row.last_payment_amount)
                if row.last_payment_amount is not None
                else None
            ),
            is_active=bool(row.is_active),
        )
        for row in rows
    )

    summary_row = session.execute(
        select(
            func.count(Apartment.id).label("apartment_count"),
            func.coalesce(func.sum(resident_count), 0).label("resident_count"),
            func.coalesce(func.sum(outstanding_debt), zero_money).label(
                "outstanding_debt"
            ),
            func.coalesce(func.sum(current_charges), zero_money).label(
                "current_charges"
            ),
            func.coalesce(func.sum(current_payments), zero_money).label(
                "current_payments"
            ),
        )
        .outerjoin(residents, residents.c.apartment_id == Apartment.id)
        .outerjoin(charges, charges.c.apartment_id == Apartment.id)
        .outerjoin(allocations, allocations.c.apartment_id == Apartment.id)
        .outerjoin(monthly_charges, monthly_charges.c.apartment_id == Apartment.id)
        .outerjoin(monthly_payments, monthly_payments.c.apartment_id == Apartment.id)
        .where(*base_conditions)
    ).one()
    building_charges = money_decimal(summary_row.current_charges)
    building_payments = money_decimal(summary_row.current_payments)
    collection_rate = (
        (building_payments / building_charges * Decimal("100")).quantize(
            Decimal("0.01")
        )
        if building_charges > MONEY_ZERO
        else None
    )
    last_charge_date = session.scalar(
        select(func.max(Charge.due_date)).where(
            Charge.organization_id == organization_id,
            Charge.building_id == building_id,
            Charge.status == ChargeStatus.POSTED,
        )
    )
    last_payment_date = session.scalar(
        select(func.max(Payment.payment_date)).where(
            Payment.organization_id == organization_id,
            Payment.building_id == building_id,
            Payment.status == PaymentStatus.POSTED,
        )
    )
    movement_dates = [
        movement_date
        for movement_date in (last_charge_date, last_payment_date)
        if movement_date is not None
    ]
    summary = BuildingDetailSummary(
        id=building.id,
        name=building.name,
        address=_address(building),
        is_active=building.is_active,
        apartment_count=int(summary_row.apartment_count),
        active_resident_count=int(summary_row.resident_count),
        outstanding_debt=money_decimal(summary_row.outstanding_debt),
        current_month_charges=building_charges,
        current_month_payments=building_payments,
        collection_rate=collection_rate,
        last_financial_movement_date=max(movement_dates) if movement_dates else None,
        period_label=month_start.strftime("%m.%Y"),
    )
    return OrganizationBuildingDetail(
        building=summary,
        apartments=ApartmentDetailPage(
            items=apartment_items,
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
            search=search,
            sort=sort,
            direction=direction,
        ),
        movements=_recent_movements(
            session,
            organization_id=organization_id,
            building_id=building_id,
        ),
    )

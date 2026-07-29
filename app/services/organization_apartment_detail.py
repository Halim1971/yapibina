from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Generic, TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import String, and_, case, cast, func, or_, select
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
    PaymentMethod,
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

PAGE_SIZES = frozenset({20, 50, 100})
T = TypeVar("T")
PAYMENT_METHOD_LABELS = {
    PaymentMethod.CASH: "Nakit",
    PaymentMethod.BANK_TRANSFER: "Havale/EFT",
    PaymentMethod.CARD: "Kart",
    PaymentMethod.OTHER: "Diğer",
}


@dataclass(frozen=True, slots=True)
class ApartmentIdentity:
    id: uuid.UUID
    building_id: uuid.UUID
    building_name: str
    label: str
    number: str
    block: str | None
    floor: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class ActiveResident:
    id: uuid.UUID
    display_name: str
    email: str
    phone: str | None
    starts_at: datetime


@dataclass(frozen=True, slots=True)
class ApartmentFinancialSummary:
    outstanding_debt: Decimal
    current_month_charges: Decimal
    current_month_payments: Decimal
    collection_rate: Decimal | None
    last_charge_date: date | None
    last_payment_date: date | None
    last_payment_amount: Decimal | None
    total_charges: Decimal
    total_payments: Decimal
    total_allocated: Decimal
    total_unallocated: Decimal


@dataclass(frozen=True, slots=True)
class ChargeHistoryItem:
    id: uuid.UUID
    title: str
    charge_type: str
    period_label: str
    created_at: datetime
    due_date: date
    amount: Decimal
    allocated_amount: Decimal
    outstanding_amount: Decimal
    status_label: str


@dataclass(frozen=True, slots=True)
class PaymentHistoryItem:
    id: uuid.UUID
    payment_date: date
    amount: Decimal
    note: str
    method_label: str
    allocated_amount: Decimal
    unallocated_amount: Decimal


@dataclass(frozen=True, slots=True)
class BalanceMovement:
    occurred_at: datetime
    kind: str
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal
    source_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class HistoryPage(Generic[T]):
    items: tuple[T, ...]
    page: int
    pages: int
    per_page: int
    total: int
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
class MovementPage:
    items: tuple[BalanceMovement, ...]
    page: int
    pages: int
    per_page: int
    total: int

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


@dataclass(frozen=True, slots=True)
class OrganizationApartmentDetail:
    identity: ApartmentIdentity
    residents: tuple[ActiveResident, ...]
    financial: ApartmentFinancialSummary
    charges: HistoryPage[ChargeHistoryItem]
    payments: HistoryPage[PaymentHistoryItem]
    movements: MovementPage


def _options(
    search: str,
    sort: str,
    direction: str,
    page: int,
    per_page: int,
    allowed_sorts: frozenset[str],
    default_sort: str,
) -> tuple[str, str, str, int, int]:
    return (
        search.strip(),
        sort if sort in allowed_sorts else default_sort,
        direction if direction in {"asc", "desc"} else "desc",
        max(page, 1),
        per_page if per_page in PAGE_SIZES else 20,
    )


def _pages(total: int, page: int, per_page: int) -> tuple[int, int]:
    pages = math.ceil(total / per_page) if total else 0
    return (min(page, pages) if pages else 1), pages


def _to_local(value: datetime, timezone_name: str) -> datetime:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(ZoneInfo(timezone_name))


def _identity(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> ApartmentIdentity:
    row = session.execute(
        select(Apartment, Building)
        .join(
            Building,
            and_(
                Building.id == Apartment.building_id,
                Building.organization_id == organization_id,
            ),
        )
        .where(
            Apartment.id == apartment_id,
            Apartment.organization_id == organization_id,
            Apartment.building_id == building_id,
        )
    ).one_or_none()
    if row is None:
        raise ServiceValidationError("Daire bulunamadı.")
    apartment, building = row
    return ApartmentIdentity(
        id=apartment.id,
        building_id=building.id,
        building_name=building.name,
        label=apartment.unit_code or apartment.number,
        number=apartment.number,
        block=apartment.block,
        floor=apartment.floor,
        is_active=apartment.is_active,
    )


def _residents(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
    now: datetime,
    timezone_name: str,
) -> tuple[ActiveResident, ...]:
    rows = session.execute(
        select(
            User.id,
            User.first_name,
            User.last_name,
            User.email,
            User.phone,
            func.min(ApartmentMembership.starts_at).label("starts_at"),
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
            ApartmentMembership.apartment_id == apartment_id,
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
        .group_by(
            User.id,
            User.first_name,
            User.last_name,
            User.email,
            User.phone,
        )
        .order_by(User.first_name, User.last_name, User.id)
    ).all()
    return tuple(
        ActiveResident(
            id=row.id,
            display_name=f"{row.first_name} {row.last_name}".strip() or row.email,
            email=row.email,
            phone=row.phone,
            starts_at=_to_local(row.starts_at, timezone_name),
        )
        for row in rows
    )


def _allocation_sum_subquery(
    organization_id: uuid.UUID,
    *,
    by: str,
) -> Subquery:
    group_column = (
        PaymentAllocation.charge_id
        if by == "charge"
        else PaymentAllocation.payment_id
    )
    return (
        select(
            group_column.label("source_id"),
            func.sum(PaymentAllocation.amount).label("allocated"),
        )
        .join(
            Payment,
            and_(
                Payment.id == PaymentAllocation.payment_id,
                Payment.organization_id == organization_id,
                Payment.status == PaymentStatus.POSTED,
            ),
        )
        .join(
            Charge,
            and_(
                Charge.id == PaymentAllocation.charge_id,
                Charge.organization_id == organization_id,
                Charge.status == ChargeStatus.POSTED,
            ),
        )
        .where(PaymentAllocation.organization_id == organization_id)
        .group_by(group_column)
        .subquery()
    )


def _financial_summary(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
    month_start: date,
    month_end: date,
) -> ApartmentFinancialSummary:
    charge_totals = session.execute(
        select(
            func.coalesce(func.sum(Charge.original_amount), 0).label("total"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            period_charge_filter(month_start, month_end),
                            Charge.original_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("current"),
            func.max(Charge.due_date).label("last_date"),
        ).where(
            Charge.organization_id == organization_id,
            Charge.apartment_id == apartment_id,
            Charge.status == ChargeStatus.POSTED,
        )
    ).one()
    payment_totals = session.execute(
        select(
            func.coalesce(func.sum(Payment.amount), 0).label("total"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                Payment.payment_date >= month_start,
                                Payment.payment_date < month_end,
                            ),
                            Payment.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("current"),
        ).where(
            Payment.organization_id == organization_id,
            Payment.apartment_id == apartment_id,
            Payment.status == PaymentStatus.POSTED,
        )
    ).one()
    total_charges = money_decimal(charge_totals.total)
    total_payments = money_decimal(payment_totals.total)
    total_allocated = money_decimal(
        session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
            .join(
                Payment,
                and_(
                    Payment.id == PaymentAllocation.payment_id,
                    Payment.organization_id == organization_id,
                    Payment.apartment_id == apartment_id,
                    Payment.status == PaymentStatus.POSTED,
                ),
            )
            .join(
                Charge,
                and_(
                    Charge.id == PaymentAllocation.charge_id,
                    Charge.organization_id == organization_id,
                    Charge.apartment_id == apartment_id,
                    Charge.status == ChargeStatus.POSTED,
                ),
            )
            .where(PaymentAllocation.organization_id == organization_id)
        )
    )
    current_charges = money_decimal(charge_totals.current)
    current_payments = money_decimal(payment_totals.current)
    last_payment = session.execute(
        select(Payment.payment_date, Payment.amount)
        .where(
            Payment.organization_id == organization_id,
            Payment.apartment_id == apartment_id,
            Payment.status == PaymentStatus.POSTED,
        )
        .order_by(
            Payment.payment_date.desc(),
            Payment.created_at.desc(),
            Payment.id.desc(),
        )
        .limit(1)
    ).one_or_none()
    return ApartmentFinancialSummary(
        outstanding_debt=max(total_charges - total_allocated, MONEY_ZERO),
        current_month_charges=current_charges,
        current_month_payments=current_payments,
        collection_rate=(
            (current_payments / current_charges * Decimal("100")).quantize(
                Decimal("0.01")
            )
            if current_charges > MONEY_ZERO
            else None
        ),
        last_charge_date=charge_totals.last_date,
        last_payment_date=last_payment.payment_date if last_payment else None,
        last_payment_amount=money_decimal(last_payment.amount) if last_payment else None,
        total_charges=total_charges,
        total_payments=total_payments,
        total_allocated=total_allocated,
        total_unallocated=max(total_payments - total_allocated, MONEY_ZERO),
    )


def _charge_status(
    *,
    amount: Decimal,
    allocated: Decimal,
    due_date: date,
    today: date,
) -> str:
    if allocated >= amount:
        return "Ödendi"
    if allocated > MONEY_ZERO:
        return "Kısmi Ödendi"
    if due_date < today:
        return "Vadesi Geçmiş"
    return "Ödenmedi"


def _charge_history(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
    timezone_name: str,
    today: date,
    search: str,
    sort: str,
    direction: str,
    page: int,
    per_page: int,
) -> HistoryPage[ChargeHistoryItem]:
    search, sort, direction, page, per_page = _options(
        search,
        sort,
        direction,
        page,
        per_page,
        frozenset({"date", "amount", "outstanding", "due_date"}),
        "date",
    )
    allocations = _allocation_sum_subquery(organization_id, by="charge")
    allocated = func.coalesce(allocations.c.allocated, 0)
    outstanding = Charge.original_amount - allocated
    conditions: list[ColumnElement[bool]] = [
        Charge.organization_id == organization_id,
        Charge.apartment_id == apartment_id,
        Charge.status == ChargeStatus.POSTED,
    ]
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                Charge.title.ilike(pattern),
                Charge.description.ilike(pattern),
                cast(Charge.charge_type, String).ilike(pattern),
            )
        )
    total = int(session.scalar(select(func.count(Charge.id)).where(*conditions)) or 0)
    page, pages = _pages(total, page, per_page)
    expressions = {
        "date": Charge.due_date,
        "amount": Charge.original_amount,
        "outstanding": outstanding,
        "due_date": Charge.due_date,
    }
    primary = expressions[sort]
    ordering = primary.desc() if direction == "desc" else primary.asc()
    rows = session.execute(
        select(Charge, allocated.label("allocated"))
        .outerjoin(allocations, allocations.c.source_id == Charge.id)
        .where(*conditions)
        .order_by(ordering, Charge.due_date.desc(), Charge.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    items = tuple(
        ChargeHistoryItem(
            id=row.Charge.id,
            title=row.Charge.title,
            charge_type=row.Charge.charge_type.value,
            period_label=(
                f"{row.Charge.period_month:02d}.{row.Charge.period_year}"
                if row.Charge.period_year and row.Charge.period_month
                else row.Charge.due_date.strftime("%m.%Y")
            ),
            created_at=_to_local(row.Charge.created_at, timezone_name),
            due_date=row.Charge.due_date,
            amount=money_decimal(row.Charge.original_amount),
            allocated_amount=money_decimal(row.allocated),
            outstanding_amount=max(
                money_decimal(row.Charge.original_amount) - money_decimal(row.allocated),
                MONEY_ZERO,
            ),
            status_label=_charge_status(
                amount=money_decimal(row.Charge.original_amount),
                allocated=money_decimal(row.allocated),
                due_date=row.Charge.due_date,
                today=today,
            ),
        )
        for row in rows
    )
    return HistoryPage(items, page, pages, per_page, total, search, sort, direction)


def _payment_history(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
    search: str,
    sort: str,
    direction: str,
    page: int,
    per_page: int,
) -> HistoryPage[PaymentHistoryItem]:
    search, sort, direction, page, per_page = _options(
        search,
        sort,
        direction,
        page,
        per_page,
        frozenset({"date", "amount", "allocated", "unallocated"}),
        "date",
    )
    allocations = _allocation_sum_subquery(organization_id, by="payment")
    allocated = func.coalesce(allocations.c.allocated, 0)
    unallocated = Payment.amount - allocated
    conditions: list[ColumnElement[bool]] = [
        Payment.organization_id == organization_id,
        Payment.apartment_id == apartment_id,
        Payment.status == PaymentStatus.POSTED,
    ]
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                Payment.description.ilike(pattern),
                Payment.reference.ilike(pattern),
                cast(Payment.payment_method, String).ilike(pattern),
            )
        )
    total = int(session.scalar(select(func.count(Payment.id)).where(*conditions)) or 0)
    page, pages = _pages(total, page, per_page)
    expressions = {
        "date": Payment.payment_date,
        "amount": Payment.amount,
        "allocated": allocated,
        "unallocated": unallocated,
    }
    primary = expressions[sort]
    ordering = primary.desc() if direction == "desc" else primary.asc()
    rows = session.execute(
        select(Payment, allocated.label("allocated"))
        .outerjoin(allocations, allocations.c.source_id == Payment.id)
        .where(*conditions)
        .order_by(ordering, Payment.payment_date.desc(), Payment.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    items = tuple(
        PaymentHistoryItem(
            id=row.Payment.id,
            payment_date=row.Payment.payment_date,
            amount=money_decimal(row.Payment.amount),
            note=row.Payment.description or row.Payment.reference or "Ödeme",
            method_label=PAYMENT_METHOD_LABELS[row.Payment.payment_method],
            allocated_amount=money_decimal(row.allocated),
            unallocated_amount=max(
                money_decimal(row.Payment.amount) - money_decimal(row.allocated),
                MONEY_ZERO,
            ),
        )
        for row in rows
    )
    return HistoryPage(items, page, pages, per_page, total, search, sort, direction)


def _movements(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
    timezone_name: str,
    page: int,
    per_page: int,
) -> MovementPage:
    charges = session.execute(
        select(
            Charge.id,
            Charge.due_date,
            Charge.created_at,
            Charge.title,
            Charge.original_amount,
        ).where(
            Charge.organization_id == organization_id,
            Charge.apartment_id == apartment_id,
            Charge.status == ChargeStatus.POSTED,
        )
    ).all()
    allocations = session.execute(
        select(
            PaymentAllocation.id,
            PaymentAllocation.created_at,
            PaymentAllocation.amount,
            Charge.title,
        )
        .join(
            Charge,
            and_(
                Charge.id == PaymentAllocation.charge_id,
                Charge.organization_id == organization_id,
                Charge.apartment_id == apartment_id,
                Charge.status == ChargeStatus.POSTED,
            ),
        )
        .join(
            Payment,
            and_(
                Payment.id == PaymentAllocation.payment_id,
                Payment.organization_id == organization_id,
                Payment.apartment_id == apartment_id,
                Payment.status == PaymentStatus.POSTED,
            ),
        )
        .where(PaymentAllocation.organization_id == organization_id)
    ).all()
    entries: list[tuple[datetime, int, str, Decimal, Decimal, uuid.UUID]] = []
    for charge_row in charges:
        created = _to_local(charge_row.created_at, timezone_name)
        occurred = datetime.combine(
            charge_row.due_date,
            created.timetz(),
        )
        entries.append(
            (
                occurred,
                0,
                charge_row.title,
                money_decimal(charge_row.original_amount),
                MONEY_ZERO,
                charge_row.id,
            )
        )
    for allocation_row in allocations:
        entries.append(
            (
                _to_local(allocation_row.created_at, timezone_name),
                1,
                f"{allocation_row.title} için ödeme uygulaması",
                MONEY_ZERO,
                money_decimal(allocation_row.amount),
                allocation_row.id,
            )
        )
    running = MONEY_ZERO
    movements: list[BalanceMovement] = []
    for occurred, kind_order, description, debit, credit, source_id in sorted(
        entries,
        key=lambda item: (item[0], item[1], str(item[5])),
    ):
        running = (running + debit - credit).quantize(Decimal("0.01"))
        movements.append(
            BalanceMovement(
                occurred_at=occurred,
                kind="Borç" if kind_order == 0 else "Ödeme Uygulaması",
                description=description,
                debit=debit,
                credit=credit,
                running_balance=running,
                source_id=source_id,
            )
        )
    safe_per_page = per_page if per_page in PAGE_SIZES else 20
    safe_page = max(page, 1)
    safe_page, pages = _pages(len(movements), safe_page, safe_per_page)
    newest_first = tuple(reversed(movements))
    start = (safe_page - 1) * safe_per_page
    return MovementPage(
        items=newest_first[start : start + safe_per_page],
        page=safe_page,
        pages=pages,
        per_page=safe_per_page,
        total=len(movements),
    )


def get_organization_apartment_detail(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    apartment_id: uuid.UUID,
    timezone_name: str,
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
    reference_date: date | None = None,
    include_residents: bool = True,
) -> OrganizationApartmentDetail:
    identity = _identity(
        session,
        organization_id=organization_id,
        building_id=building_id,
        apartment_id=apartment_id,
    )
    today = reference_date or local_today(timezone_name)
    month_start, month_end = month_range(today)
    now = datetime.now(timezone.utc)
    return OrganizationApartmentDetail(
        identity=identity,
        residents=(
            _residents(
                session,
                organization_id=organization_id,
                apartment_id=apartment_id,
                now=now,
                timezone_name=timezone_name,
            )
            if include_residents
            else ()
        ),
        financial=_financial_summary(
            session,
            organization_id=organization_id,
            apartment_id=apartment_id,
            month_start=month_start,
            month_end=month_end,
        ),
        charges=_charge_history(
            session,
            organization_id=organization_id,
            apartment_id=apartment_id,
            timezone_name=timezone_name,
            today=today,
            search=charge_search,
            sort=charge_sort,
            direction=charge_direction,
            page=charge_page,
            per_page=charge_per_page,
        ),
        payments=_payment_history(
            session,
            organization_id=organization_id,
            apartment_id=apartment_id,
            search=payment_search,
            sort=payment_sort,
            direction=payment_direction,
            page=payment_page,
            per_page=payment_per_page,
        ),
        movements=_movements(
            session,
            organization_id=organization_id,
            apartment_id=apartment_id,
            timezone_name=timezone_name,
            page=movement_page,
            per_page=movement_per_page,
        ),
    )

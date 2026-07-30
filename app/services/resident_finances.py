from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select

from app.models import (
    Apartment,
    ApartmentExpenseContribution,
    ApartmentMembership,
    Building,
    BuildingBankTransaction,
    BuildingExpense,
    Charge,
    ChargeStatus,
    OrganizationMembership,
    OrganizationMembershipRole,
    Payment,
    PaymentAllocation,
    PaymentMethod,
    PaymentStatus,
    User,
    UserStatus,
)
from app.models.base import utc_now
from app.services import EntityNotFoundError, SessionLike

ZERO = Decimal("0.00")
PAYMENT_METHOD_LABELS = {
    PaymentMethod.CASH: "Nakit",
    PaymentMethod.BANK_TRANSFER: "Havale/EFT",
    PaymentMethod.CARD: "Kart",
    PaymentMethod.OTHER: "Diğer",
}


@dataclass(frozen=True, slots=True)
class ResidentApartment:
    id: uuid.UUID
    building_id: uuid.UUID
    building_name: str
    apartment_label: str
    block: str | None
    floor: str | None


@dataclass(frozen=True, slots=True)
class ResidentPayment:
    payment_date: date
    amount: Decimal
    method_label: str
    note: str | None


@dataclass(frozen=True, slots=True)
class ResidentStatementRow:
    occurred_on: date
    description: str
    debt_amount: Decimal
    payment_amount: Decimal
    running_balance: Decimal


@dataclass(frozen=True, slots=True)
class ResidentDashboard:
    apartment: ResidentApartment | None
    apartments: tuple[ResidentApartment, ...]
    current_debt: Decimal
    overdue_debt: Decimal
    total_charges: Decimal
    total_payments: Decimal
    unallocated_payment: Decimal
    latest_payment: ResidentPayment | None
    latest_charge_date: date | None
    latest_movement_date: date | None
    recent_payments: tuple[ResidentPayment, ...]
    recent_transactions: tuple[ResidentStatementRow, ...]


@dataclass(frozen=True, slots=True)
class PaginatedPayments:
    items: tuple[ResidentPayment, ...]
    page: int
    pages: int


@dataclass(frozen=True, slots=True)
class StatementFilters:
    query: str = ""
    date_from: date | None = None
    date_to: date | None = None
    movement_type: str = "all"


@dataclass(frozen=True, slots=True)
class FinanceStatementViewModel:
    items: tuple[ResidentStatementRow, ...]
    page: int
    pages: int
    total_items: int
    filters: StatementFilters
    current_balance: Decimal
    total_charges: Decimal
    total_payments: Decimal
    latest_payment_date: date | None
    latest_charge_date: date | None


PaginatedStatement = FinanceStatementViewModel


@dataclass(frozen=True, slots=True)
class MonthlyDueSummary:
    year: int
    month: int
    charged: Decimal
    paid: Decimal
    remaining: Decimal
    status_label: str


@dataclass(frozen=True, slots=True)
class MonthlyDueDetail:
    apartment: ResidentApartment
    year: int
    month: int
    items: tuple[tuple[str, Decimal], ...]
    charged: Decimal
    paid: Decimal
    remaining: Decimal


@dataclass(frozen=True, slots=True)
class BankMovementItem:
    transaction_date: date
    description: str
    inflow: Decimal
    outflow: Decimal
    balance: Decimal
    category: str


@dataclass(frozen=True, slots=True)
class ExpenseDistributionItem:
    expense_date: date
    expense_month: date
    category: str
    payment_method: str
    total_amount: Decimal
    source_key: str
    contribution: Decimal
    description: str


def format_try(value: Decimal) -> str:
    grouped = f"{value:,.2f}"
    return grouped.replace(",", "_").replace(".", ",").replace("_", ".") + " TL"


def _require_resident_identity(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    now = utc_now()
    permitted = session.scalar(
        select(User.id)
        .join(
            OrganizationMembership,
            OrganizationMembership.user_id == User.id,
        )
        .where(
            User.id == user_id,
            User.status == UserStatus.ACTIVE,
            User.is_platform_super_admin.is_(False),
            OrganizationMembership.organization_id == organization_id,
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
    if permitted is None:
        raise EntityNotFoundError("İkamet eden erişimi bulunamadı.")


def list_resident_apartments(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[ResidentApartment]:
    _require_resident_identity(
        session,
        organization_id=organization_id,
        user_id=user_id,
    )
    now = utc_now()
    rows = session.execute(
        select(Apartment, Building)
        .join(
            ApartmentMembership,
            ApartmentMembership.apartment_id == Apartment.id,
        )
        .join(
            Building,
            (Building.id == Apartment.building_id)
            & (Building.organization_id == Apartment.organization_id),
        )
        .where(
            Apartment.organization_id == organization_id,
            Apartment.is_active.is_(True),
            Building.organization_id == organization_id,
            Building.is_active.is_(True),
            ApartmentMembership.organization_id == organization_id,
            ApartmentMembership.user_id == user_id,
            ApartmentMembership.is_active.is_(True),
            ApartmentMembership.starts_at <= now,
            or_(
                ApartmentMembership.ends_at.is_(None),
                ApartmentMembership.ends_at >= now,
            ),
        )
        .order_by(
            Building.name,
            Apartment.block,
            Apartment.floor,
            func.length(func.coalesce(Apartment.unit_code, Apartment.number)),
            func.coalesce(Apartment.unit_code, Apartment.number),
            Apartment.id,
        )
    )
    return [
        ResidentApartment(
            id=apartment.id,
            building_id=building.id,
            building_name=building.name,
            apartment_label=apartment.unit_code or apartment.number,
            block=apartment.block,
            floor=apartment.floor,
        )
        for apartment, building in rows
    ]


def resolve_resident_apartment(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    apartment_id: uuid.UUID | None,
) -> tuple[ResidentApartment | None, tuple[ResidentApartment, ...]]:
    apartments = tuple(
        list_resident_apartments(
            session,
            organization_id=organization_id,
            user_id=user_id,
        )
    )
    if apartment_id is None:
        return (apartments[0] if apartments else None), apartments
    selected = next((item for item in apartments if item.id == apartment_id), None)
    if selected is None:
        raise EntityNotFoundError("Bağımsız bölüm bulunamadı.")
    return selected, apartments


def get_monthly_due_summary(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    apartment_id: uuid.UUID,
    limit: int = 6,
) -> tuple[MonthlyDueSummary, ...]:
    selected, _ = resolve_resident_apartment(
        session,
        organization_id=organization_id,
        user_id=user_id,
        apartment_id=apartment_id,
    )
    if selected is None:
        return ()
    allocated = (
        select(
            PaymentAllocation.charge_id,
            func.coalesce(func.sum(PaymentAllocation.amount), 0).label("paid"),
        )
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(
            PaymentAllocation.organization_id == organization_id,
            Payment.organization_id == organization_id,
            Payment.apartment_id == apartment_id,
            Payment.status == PaymentStatus.POSTED,
        )
        .group_by(PaymentAllocation.charge_id)
        .subquery()
    )
    rows = session.execute(
        select(
            Charge.period_year,
            Charge.period_month,
            Charge.original_amount,
            func.coalesce(allocated.c.paid, 0),
        )
        .outerjoin(allocated, allocated.c.charge_id == Charge.id)
        .where(
            Charge.organization_id == organization_id,
            Charge.apartment_id == apartment_id,
            Charge.status == ChargeStatus.POSTED,
            Charge.period_year.is_not(None),
            Charge.period_month.is_not(None),
        )
        .order_by(Charge.period_year.desc(), Charge.period_month.desc(), Charge.id)
        .limit(limit)
    )
    result = []
    for year, month, amount, paid_value in rows:
        charged = Decimal(amount).quantize(Decimal("0.01"))
        paid = min(Decimal(paid_value).quantize(Decimal("0.01")), charged)
        remaining = max(charged - paid, ZERO)
        status = (
            "Ödendi"
            if remaining == ZERO
            else "Kısmi Ödendi"
            if paid > ZERO
            else "Ödenmedi"
        )
        result.append(
            MonthlyDueSummary(
                year=int(year),
                month=int(month),
                charged=charged,
                paid=paid,
                remaining=remaining,
                status_label=status,
            )
        )
    return tuple(result)


def get_monthly_due_detail(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    apartment_id: uuid.UUID,
    year: int,
    month: int,
) -> MonthlyDueDetail:
    selected, _ = resolve_resident_apartment(
        session,
        organization_id=organization_id,
        user_id=user_id,
        apartment_id=apartment_id,
    )
    if selected is None:
        raise EntityNotFoundError("Bağımsız bölüm bulunamadı.")
    summary = next(
        (
            item
            for item in get_monthly_due_summary(
                session,
                organization_id=organization_id,
                user_id=user_id,
                apartment_id=apartment_id,
                limit=120,
            )
            if item.year == year and item.month == month
        ),
        None,
    )
    if summary is None:
        raise EntityNotFoundError("Aidat dönemi bulunamadı.")
    base_month = date(year - 1, 12, 1) if month == 1 else date(year, month - 1, 1)
    rows = session.execute(
        select(
            BuildingExpense.category,
            func.sum(ApartmentExpenseContribution.amount),
        )
        .join(
            ApartmentExpenseContribution,
            ApartmentExpenseContribution.expense_id == BuildingExpense.id,
        )
        .where(
            BuildingExpense.organization_id == organization_id,
            BuildingExpense.building_id == selected.building_id,
            BuildingExpense.expense_month == base_month,
            ApartmentExpenseContribution.organization_id == organization_id,
            ApartmentExpenseContribution.apartment_id == apartment_id,
        )
        .group_by(BuildingExpense.category)
        .order_by(BuildingExpense.category)
    )
    return MonthlyDueDetail(
        apartment=selected,
        year=year,
        month=month,
        items=tuple(
            (category, Decimal(amount).quantize(Decimal("0.01")))
            for category, amount in rows
        ),
        charged=summary.charged,
        paid=summary.paid,
        remaining=summary.remaining,
    )


def list_resident_bank_movements(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    building_id: uuid.UUID,
    page: int,
    per_page: int,
) -> tuple[tuple[BankMovementItem, ...], int]:
    apartments = list_resident_apartments(
        session, organization_id=organization_id, user_id=user_id
    )
    if building_id not in {item.building_id for item in apartments}:
        raise EntityNotFoundError("Bina bulunamadı.")
    page = max(page, 1)
    per_page = per_page if per_page in {20, 50, 100} else 20
    conditions = (
        BuildingBankTransaction.organization_id == organization_id,
        BuildingBankTransaction.building_id == building_id,
    )
    total = int(
        session.scalar(select(func.count()).select_from(BuildingBankTransaction).where(*conditions))
        or 0
    )
    rows = session.execute(
        select(BuildingBankTransaction)
        .where(*conditions)
        .order_by(
            BuildingBankTransaction.transaction_date.desc(),
            BuildingBankTransaction.id.desc(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).scalars()
    return (
        tuple(
            BankMovementItem(
                transaction_date=item.transaction_date,
                description=item.description,
                inflow=Decimal(item.inflow),
                outflow=Decimal(item.outflow),
                balance=Decimal(item.balance),
                category=item.category,
            )
            for item in rows
        ),
        total,
    )


def list_resident_expenses(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    apartment_id: uuid.UUID,
    page: int,
    per_page: int,
) -> tuple[tuple[ExpenseDistributionItem, ...], int]:
    selected, _ = resolve_resident_apartment(
        session,
        organization_id=organization_id,
        user_id=user_id,
        apartment_id=apartment_id,
    )
    if selected is None:
        raise EntityNotFoundError("Bağımsız bölüm bulunamadı.")
    page = max(page, 1)
    per_page = per_page if per_page in {20, 50, 100} else 20
    conditions = (
        BuildingExpense.organization_id == organization_id,
        BuildingExpense.building_id == selected.building_id,
        ApartmentExpenseContribution.organization_id == organization_id,
        ApartmentExpenseContribution.apartment_id == apartment_id,
    )
    base = (
        select(BuildingExpense, ApartmentExpenseContribution.amount.label("share"))
        .join(
            ApartmentExpenseContribution,
            ApartmentExpenseContribution.expense_id == BuildingExpense.id,
        )
        .where(*conditions)
    )
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = session.execute(
        base.order_by(BuildingExpense.expense_date.desc(), BuildingExpense.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return (
        tuple(
            ExpenseDistributionItem(
                expense_date=expense.expense_date,
                expense_month=expense.expense_month,
                category=expense.category,
                payment_method=expense.payment_method,
                total_amount=Decimal(expense.amount),
                source_key=expense.source_key,
                contribution=Decimal(share),
                description=expense.description,
            )
            for expense, share in rows
        ),
        total,
    )


def _payment_allocations(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> dict[uuid.UUID, Decimal]:
    rows = session.execute(
        select(
            PaymentAllocation.payment_id,
            func.sum(PaymentAllocation.amount),
        )
        .join(Charge, Charge.id == PaymentAllocation.charge_id)
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(
            PaymentAllocation.organization_id == organization_id,
            Charge.organization_id == organization_id,
            Charge.apartment_id == apartment_id,
            Charge.status == ChargeStatus.POSTED,
            Payment.organization_id == organization_id,
            Payment.apartment_id == apartment_id,
            Payment.status == PaymentStatus.POSTED,
        )
        .group_by(PaymentAllocation.payment_id)
    )
    return {
        payment_id: Decimal(amount).quantize(Decimal("0.01"))
        for payment_id, amount in rows
    }


def _charge_allocations(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> dict[uuid.UUID, Decimal]:
    rows = session.execute(
        select(
            PaymentAllocation.charge_id,
            func.sum(PaymentAllocation.amount),
        )
        .join(Charge, Charge.id == PaymentAllocation.charge_id)
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(
            PaymentAllocation.organization_id == organization_id,
            Charge.organization_id == organization_id,
            Charge.apartment_id == apartment_id,
            Charge.status == ChargeStatus.POSTED,
            Payment.organization_id == organization_id,
            Payment.apartment_id == apartment_id,
            Payment.status == PaymentStatus.POSTED,
        )
        .group_by(PaymentAllocation.charge_id)
    )
    return {
        charge_id: Decimal(amount).quantize(Decimal("0.01"))
        for charge_id, amount in rows
    }


def _payment_view(payment: Payment) -> ResidentPayment:
    return ResidentPayment(
        payment_date=payment.payment_date,
        amount=payment.amount,
        method_label=PAYMENT_METHOD_LABELS[payment.payment_method],
        note=payment.description or payment.reference,
    )


def _posted_payments(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> list[Payment]:
    return list(
        session.scalars(
            select(Payment)
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
        )
    )


def _posted_charges(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> list[Charge]:
    return list(
        session.scalars(
            select(Charge)
            .where(
                Charge.organization_id == organization_id,
                Charge.apartment_id == apartment_id,
                Charge.status == ChargeStatus.POSTED,
            )
            .order_by(Charge.due_date, Charge.created_at, Charge.id)
        )
    )


def _statement_from_records(
    *,
    charges: list[Charge],
    payments: list[Payment],
    allocations: dict[uuid.UUID, Decimal],
) -> tuple[ResidentStatementRow, ...]:
    entries: list[tuple[date, datetime, int, str, Decimal, Decimal]] = [
        (
            charge.due_date,
            charge.created_at,
            0,
            charge.title,
            charge.original_amount,
            ZERO,
        )
        for charge in charges
    ]
    for payment in payments:
        allocated = allocations.get(payment.id, ZERO)
        unallocated = (payment.amount - allocated).quantize(Decimal("0.01"))
        description = f"{PAYMENT_METHOD_LABELS[payment.payment_method]} ile ödeme"
        if unallocated > ZERO:
            description += " (kullanılmamış tutar ayrıca gösterilir)"
        entries.append(
            (
                payment.payment_date,
                payment.created_at,
                1,
                description,
                ZERO,
                allocated,
            )
        )

    running = ZERO
    result: list[ResidentStatementRow] = []
    for occurred_on, _, _, description, debt, paid in sorted(
        entries,
        key=lambda item: (item[0], item[1], item[2], item[3]),
    ):
        running = (running + debt - paid).quantize(Decimal("0.01"))
        result.append(
            ResidentStatementRow(
                occurred_on=occurred_on,
                description=description,
                debt_amount=debt,
                payment_amount=paid,
                running_balance=running,
            )
        )
    return tuple(result)


def _statement(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> tuple[ResidentStatementRow, ...]:
    charges = _posted_charges(
        session,
        organization_id=organization_id,
        apartment_id=apartment_id,
    )
    payments = _posted_payments(
        session,
        organization_id=organization_id,
        apartment_id=apartment_id,
    )
    allocations = _payment_allocations(
        session,
        organization_id=organization_id,
        apartment_id=apartment_id,
    )
    return _statement_from_records(
        charges=charges,
        payments=payments,
        allocations=allocations,
    )


def get_resident_payments(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    apartment_id: uuid.UUID,
    page: int = 1,
    per_page: int = 20,
) -> PaginatedPayments:
    selected, _ = resolve_resident_apartment(
        session,
        organization_id=organization_id,
        user_id=user_id,
        apartment_id=apartment_id,
    )
    if selected is None:
        raise EntityNotFoundError("Bağımsız bölüm bulunamadı.")
    payments = _posted_payments(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    safe_page = max(page, 1)
    pages = max(math.ceil(len(payments) / per_page), 1)
    start = (safe_page - 1) * per_page
    return PaginatedPayments(
        items=tuple(_payment_view(item) for item in payments[start : start + per_page]),
        page=safe_page,
        pages=pages,
    )


def get_resident_account_statement(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    apartment_id: uuid.UUID,
    page: int = 1,
    per_page: int = 20,
    filters: StatementFilters | None = None,
) -> FinanceStatementViewModel:
    selected, _ = resolve_resident_apartment(
        session,
        organization_id=organization_id,
        user_id=user_id,
        apartment_id=apartment_id,
    )
    if selected is None:
        raise EntityNotFoundError("Bağımsız bölüm bulunamadı.")
    active_filters = filters or StatementFilters()
    charges = _posted_charges(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    payments = _posted_payments(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    allocations = _payment_allocations(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    statement = _statement_from_records(
        charges=charges,
        payments=payments,
        allocations=allocations,
    )
    query = active_filters.query.strip().casefold()
    allowed_types = {"all", "debt", "payment"}
    movement_type = (
        active_filters.movement_type
        if active_filters.movement_type in allowed_types
        else "all"
    )
    normalized_filters = StatementFilters(
        query=active_filters.query.strip(),
        date_from=active_filters.date_from,
        date_to=active_filters.date_to,
        movement_type=movement_type,
    )
    filtered = tuple(
        row
        for row in statement
        if (not query or query in row.description.casefold())
        and (
            normalized_filters.date_from is None
            or row.occurred_on >= normalized_filters.date_from
        )
        and (
            normalized_filters.date_to is None
            or row.occurred_on <= normalized_filters.date_to
        )
        and (
            movement_type == "all"
            or (movement_type == "debt" and row.debt_amount > ZERO)
            or (movement_type == "payment" and row.payment_amount > ZERO)
        )
    )
    safe_page = max(page, 1)
    safe_per_page = per_page if per_page in {20, 50, 100} else 20
    pages = max(math.ceil(len(filtered) / safe_per_page), 1)
    safe_page = min(safe_page, pages)
    start = (safe_page - 1) * safe_per_page
    return FinanceStatementViewModel(
        items=filtered[start : start + safe_per_page],
        page=safe_page,
        pages=pages,
        total_items=len(filtered),
        filters=normalized_filters,
        current_balance=statement[-1].running_balance if statement else ZERO,
        total_charges=sum(
            (charge.original_amount for charge in charges),
            start=ZERO,
        ).quantize(Decimal("0.01")),
        total_payments=sum(
            (payment.amount for payment in payments),
            start=ZERO,
        ).quantize(Decimal("0.01")),
        latest_payment_date=max(
            (payment.payment_date for payment in payments),
            default=None,
        ),
        latest_charge_date=max(
            (charge.due_date for charge in charges),
            default=None,
        ),
    )


def get_resident_dashboard(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    apartment_id: uuid.UUID | None,
) -> ResidentDashboard:
    selected, apartments = resolve_resident_apartment(
        session,
        organization_id=organization_id,
        user_id=user_id,
        apartment_id=apartment_id,
    )
    if selected is None:
        return ResidentDashboard(
            apartment=None,
            apartments=apartments,
            current_debt=ZERO,
            overdue_debt=ZERO,
            total_charges=ZERO,
            total_payments=ZERO,
            unallocated_payment=ZERO,
            latest_payment=None,
            latest_charge_date=None,
            latest_movement_date=None,
            recent_payments=(),
            recent_transactions=(),
        )
    payments = _posted_payments(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    charges = _posted_charges(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    allocations_by_payment = _payment_allocations(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    statement = _statement_from_records(
        charges=charges,
        payments=payments,
        allocations=allocations_by_payment,
    )
    allocations_by_charge = _charge_allocations(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    today = utc_now().date()
    overdue = sum(
        (
            max(
                (
                    charge.original_amount
                    - allocations_by_charge.get(charge.id, ZERO)
                ).quantize(Decimal("0.01")),
                ZERO,
            )
            for charge in charges
            if charge.due_date < today
        ),
        start=ZERO,
    ).quantize(Decimal("0.01"))
    total_charges = sum(
        (charge.original_amount for charge in charges),
        start=ZERO,
    ).quantize(Decimal("0.01"))
    total_payments = sum(
        (payment.amount for payment in payments),
        start=ZERO,
    ).quantize(Decimal("0.01"))
    total_allocated = sum(
        allocations_by_payment.values(),
        start=ZERO,
    ).quantize(Decimal("0.01"))
    current_debt = max(
        (total_charges - total_allocated).quantize(Decimal("0.01")),
        ZERO,
    )
    unallocated = max(
        (total_payments - total_allocated).quantize(Decimal("0.01")),
        ZERO,
    )
    payment_views = tuple(_payment_view(item) for item in payments[:5])
    return ResidentDashboard(
        apartment=selected,
        apartments=apartments,
        current_debt=current_debt,
        overdue_debt=overdue,
        total_charges=total_charges,
        total_payments=total_payments,
        unallocated_payment=unallocated,
        latest_payment=payment_views[0] if payment_views else None,
        latest_charge_date=max(
            (charge.due_date for charge in charges),
            default=None,
        ),
        latest_movement_date=(
            max(row.occurred_on for row in statement) if statement else None
        ),
        recent_payments=payment_views,
        recent_transactions=statement[-5:],
    )

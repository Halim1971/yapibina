from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select

from app.models import (
    Apartment,
    ApartmentMembership,
    Building,
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
from app.services.account_balances import get_apartment_balance

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
    total_payments: Decimal
    unallocated_payment: Decimal
    latest_payment: ResidentPayment | None
    recent_payments: tuple[ResidentPayment, ...]
    recent_transactions: tuple[ResidentStatementRow, ...]


@dataclass(frozen=True, slots=True)
class PaginatedPayments:
    items: tuple[ResidentPayment, ...]
    page: int
    pages: int


@dataclass(frozen=True, slots=True)
class PaginatedStatement:
    items: tuple[ResidentStatementRow, ...]
    page: int
    pages: int


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
        raise EntityNotFoundError("Resident erişimi bulunamadı.")


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
        .order_by(Building.name, Apartment.block, Apartment.floor, Apartment.id)
    )
    return [
        ResidentApartment(
            id=apartment.id,
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
        raise EntityNotFoundError("Daire bulunamadı.")
    return selected, apartments


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


def _statement(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> tuple[ResidentStatementRow, ...]:
    charges = session.scalars(
        select(Charge)
        .where(
            Charge.organization_id == organization_id,
            Charge.apartment_id == apartment_id,
            Charge.status == ChargeStatus.POSTED,
        )
        .order_by(Charge.due_date, Charge.created_at, Charge.id)
    ).all()
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
    entries: list[
        tuple[date, datetime, int, str, Decimal, Decimal]
    ] = [
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
        raise EntityNotFoundError("Daire bulunamadı.")
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
) -> PaginatedStatement:
    selected, _ = resolve_resident_apartment(
        session,
        organization_id=organization_id,
        user_id=user_id,
        apartment_id=apartment_id,
    )
    if selected is None:
        raise EntityNotFoundError("Daire bulunamadı.")
    statement = _statement(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    safe_page = max(page, 1)
    pages = max(math.ceil(len(statement) / per_page), 1)
    start = (safe_page - 1) * per_page
    return PaginatedStatement(
        items=statement[start : start + per_page],
        page=safe_page,
        pages=pages,
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
            total_payments=ZERO,
            unallocated_payment=ZERO,
            latest_payment=None,
            recent_payments=(),
            recent_transactions=(),
        )
    balance = get_apartment_balance(
        session,
        organization_id=organization_id,
        building_id=_building_id(session, organization_id, selected.id),
        apartment_id=selected.id,
    )
    payments = _posted_payments(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    statement = _statement(
        session,
        organization_id=organization_id,
        apartment_id=selected.id,
    )
    unallocated = max(
        (balance.total_payments - balance.total_allocated).quantize(
            Decimal("0.01")
        ),
        ZERO,
    )
    payment_views = tuple(_payment_view(item) for item in payments[:5])
    return ResidentDashboard(
        apartment=selected,
        apartments=apartments,
        current_debt=max(balance.total_outstanding, ZERO),
        total_payments=balance.total_payments,
        unallocated_payment=unallocated,
        latest_payment=payment_views[0] if payment_views else None,
        recent_payments=payment_views,
        recent_transactions=statement[-5:],
    )


def _building_id(
    session: SessionLike,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> uuid.UUID:
    building_id = session.scalar(
        select(Apartment.building_id).where(
            Apartment.organization_id == organization_id,
            Apartment.id == apartment_id,
            Apartment.is_active.is_(True),
        )
    )
    if building_id is None:
        raise EntityNotFoundError("Daire bulunamadı.")
    return building_id

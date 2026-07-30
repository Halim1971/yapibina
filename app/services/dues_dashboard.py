from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.models import (
    Apartment,
    Building,
    Charge,
    ChargeBatch,
    ChargeBatchStatus,
    ChargeStatus,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from app.services import EntityNotFoundError, SessionLike
from app.services.account_balances import ApartmentBalance, get_apartment_balance
from app.services.payments import get_payment_unallocated_amount
from app.services.tenancy import require_apartment

ZERO = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class DuesApartmentRow:
    apartment_id: uuid.UUID
    apartment_label: str
    floor_label: str
    charge_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    status_label: str
    status_code: str
    can_record_payment: bool


@dataclass(frozen=True, slots=True)
class DuesDashboard:
    building: Building | None
    year: int
    month: int
    batch: ChargeBatch | None
    apartment_count: int
    charged_count: int
    fully_paid_count: int
    partially_paid_count: int
    debtor_count: int
    total_charges: Decimal
    total_collected: Decimal
    total_outstanding: Decimal
    rows: tuple[DuesApartmentRow, ...]


@dataclass(frozen=True, slots=True)
class FinancialMovement:
    occurred_on: date
    description: str
    debt_amount: Decimal
    payment_amount: Decimal
    running_balance: Decimal


@dataclass(frozen=True, slots=True)
class ApartmentFinancialDetail:
    apartment: Apartment
    balance: ApartmentBalance
    unallocated_amount: Decimal
    movements: tuple[FinancialMovement, ...]


def list_active_buildings_for_dues(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
) -> list[Building]:
    return list(
        session.scalars(
            select(Building)
            .where(
                Building.organization_id == organization_id,
                Building.is_active.is_(True),
            )
            .order_by(Building.name, Building.id)
        )
    )


def get_period_batch(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    year: int,
    month: int,
) -> ChargeBatch | None:
    return session.scalar(
        select(ChargeBatch)
        .where(
            ChargeBatch.organization_id == organization_id,
            ChargeBatch.building_id == building_id,
            ChargeBatch.period_year == year,
            ChargeBatch.period_month == month,
            ChargeBatch.status != ChargeBatchStatus.CANCELLED,
        )
        .order_by(ChargeBatch.created_at.desc())
    )


def _period_financial_maps(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    year: int,
    month: int,
) -> tuple[dict[uuid.UUID, Decimal], dict[uuid.UUID, Decimal]]:
    charge_rows = session.execute(
        select(Charge.apartment_id, func.sum(Charge.original_amount))
        .where(
            Charge.organization_id == organization_id,
            Charge.building_id == building_id,
            Charge.period_year == year,
            Charge.period_month == month,
            Charge.status == ChargeStatus.POSTED,
        )
        .group_by(Charge.apartment_id)
    )
    charges = {
        apartment_id: Decimal(amount).quantize(Decimal("0.01"))
        for apartment_id, amount in charge_rows
    }
    paid_rows = session.execute(
        select(Charge.apartment_id, func.sum(PaymentAllocation.amount))
        .join(
            PaymentAllocation,
            PaymentAllocation.charge_id == Charge.id,
        )
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(
            Charge.organization_id == organization_id,
            Charge.building_id == building_id,
            Charge.period_year == year,
            Charge.period_month == month,
            Charge.status == ChargeStatus.POSTED,
            Payment.status == PaymentStatus.POSTED,
        )
        .group_by(Charge.apartment_id)
    )
    paid = {
        apartment_id: Decimal(amount).quantize(Decimal("0.01"))
        for apartment_id, amount in paid_rows
    }
    return charges, paid


def get_apartment_dues_row(
    apartment: Apartment,
    *,
    charge_amount: Decimal,
    paid_amount: Decimal,
) -> DuesApartmentRow:
    outstanding = max(charge_amount - paid_amount, ZERO)
    if charge_amount == ZERO:
        status_label, status_code = "Aidat oluşturulmadı", "not-created"
    elif outstanding == ZERO:
        status_label, status_code = "Ödendi", "paid"
    elif paid_amount > ZERO:
        status_label, status_code = "Kısmi ödendi", "partial"
    else:
        status_label, status_code = "Borçlu", "due"
    label = apartment.unit_code or apartment.number
    floor_parts = [value for value in (apartment.block, apartment.floor) if value]
    return DuesApartmentRow(
        apartment_id=apartment.id,
        apartment_label=label,
        floor_label=" / ".join(floor_parts) or "—",
        charge_amount=charge_amount,
        paid_amount=paid_amount,
        outstanding_amount=outstanding,
        status_label=status_label,
        status_code=status_code,
        can_record_payment=True,
    )


def get_dues_dashboard(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building: Building | None,
    year: int,
    month: int,
) -> DuesDashboard:
    if building is None:
        return DuesDashboard(
            building=None,
            year=year,
            month=month,
            batch=None,
            apartment_count=0,
            charged_count=0,
            fully_paid_count=0,
            partially_paid_count=0,
            debtor_count=0,
            total_charges=ZERO,
            total_collected=ZERO,
            total_outstanding=ZERO,
            rows=(),
        )
    if building.organization_id != organization_id:
        raise EntityNotFoundError("Bina bulunamadı.")
    apartments = session.scalars(
        select(Apartment)
        .where(
            Apartment.organization_id == organization_id,
            Apartment.building_id == building.id,
            Apartment.is_active.is_(True),
        )
        .order_by(
            Apartment.block,
            Apartment.floor,
            func.length(func.coalesce(Apartment.unit_code, Apartment.number)),
            func.coalesce(Apartment.unit_code, Apartment.number),
            Apartment.id,
        )
    ).all()
    charge_map, paid_map = _period_financial_maps(
        session,
        organization_id=organization_id,
        building_id=building.id,
        year=year,
        month=month,
    )
    rows = tuple(
        get_apartment_dues_row(
            apartment,
            charge_amount=charge_map.get(apartment.id, ZERO),
            paid_amount=paid_map.get(apartment.id, ZERO),
        )
        for apartment in apartments
    )
    return DuesDashboard(
        building=building,
        year=year,
        month=month,
        batch=get_period_batch(
            session,
            organization_id=organization_id,
            building_id=building.id,
            year=year,
            month=month,
        ),
        apartment_count=len(apartments),
        charged_count=sum(row.charge_amount > ZERO for row in rows),
        fully_paid_count=sum(row.status_code == "paid" for row in rows),
        partially_paid_count=sum(row.status_code == "partial" for row in rows),
        debtor_count=sum(row.status_code == "due" for row in rows),
        total_charges=sum(
            (row.charge_amount for row in rows),
            start=ZERO,
        ),
        total_collected=sum(
            (row.paid_amount for row in rows),
            start=ZERO,
        ),
        total_outstanding=sum(
            (row.outstanding_amount for row in rows),
            start=ZERO,
        ),
        rows=rows,
    )


def get_apartment_financial_detail(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> ApartmentFinancialDetail:
    apartment = require_apartment(session, organization_id, apartment_id)
    balance = get_apartment_balance(
        session,
        organization_id=organization_id,
        building_id=apartment.building_id,
        apartment_id=apartment.id,
    )
    charges = session.scalars(
        select(Charge)
        .where(
            Charge.organization_id == organization_id,
            Charge.apartment_id == apartment_id,
            Charge.status == ChargeStatus.POSTED,
        )
        .order_by(Charge.due_date, Charge.created_at, Charge.id)
    ).all()
    payments = session.scalars(
        select(Payment)
        .where(
            Payment.organization_id == organization_id,
            Payment.apartment_id == apartment_id,
            Payment.status == PaymentStatus.POSTED,
        )
        .order_by(Payment.payment_date, Payment.created_at, Payment.id)
    ).all()
    entries = [
        (charge.due_date, charge.created_at, charge.title, charge.original_amount, ZERO)
        for charge in charges
    ]
    entries.extend(
        (
            item.payment_date,
            item.created_at,
            item.description or item.reference or "Ödeme",
            ZERO,
            item.amount,
        )
        for item in payments
    )
    running = ZERO
    movements: list[FinancialMovement] = []
    for occurred_on, created_at, description, debt, received in sorted(
        entries,
        key=lambda item: (item[0], item[1], str(item[2])),
    ):
        del created_at
        running = (running + debt - received).quantize(Decimal("0.01"))
        movements.append(
            FinancialMovement(
                occurred_on=occurred_on,
                description=description,
                debt_amount=debt,
                payment_amount=received,
                running_balance=running,
            )
        )
    unallocated = sum(
        (
            get_payment_unallocated_amount(
                session,
                organization_id=organization_id,
                payment_id=item.id,
            )
            for item in payments
        ),
        start=ZERO,
    )
    return ApartmentFinancialDetail(
        apartment=apartment,
        balance=balance,
        unallocated_amount=unallocated,
        movements=tuple(movements),
    )

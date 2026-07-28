from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Apartment,
    Charge,
    ChargeBatch,
    ChargeBatchStatus,
    ChargeStatus,
    ChargeType,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from app.models.base import utc_now
from app.services import (
    ChargeHasAllocationsError,
    DuplicateChargeBatchError,
    EntityNotFoundError,
    FinancialRecordAlreadyReversedError,
    InvalidFinancialStateTransitionError,
    ServiceValidationError,
    SessionLike,
)
from app.services.financial_common import money, require_financial_scope
from app.services.tenancy import require_building, require_user


def create_charge_batch(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    period_year: int,
    period_month: int,
    title: str,
    description: str | None,
    default_amount: Decimal | str | int,
    due_date: date,
    created_by_user_id: uuid.UUID,
) -> ChargeBatch:
    require_building(session, organization_id, building_id)
    require_user(session, created_by_user_id)
    if not 1 <= period_month <= 12:
        raise ServiceValidationError("Dönem ayı 1 ile 12 arasında olmalıdır.")
    batch = ChargeBatch(
        organization_id=organization_id,
        building_id=building_id,
        period_year=period_year,
        period_month=period_month,
        title=title.strip(),
        description=description or None,
        default_amount=money(default_amount),
        due_date=due_date,
        status=ChargeBatchStatus.DRAFT,
        created_by_user_id=created_by_user_id,
    )
    session.add(batch)
    session.flush()
    return batch


def _scoped_batch(
    session: SessionLike,
    organization_id: uuid.UUID,
    batch_id: uuid.UUID,
) -> ChargeBatch:
    batch = session.scalar(
        select(ChargeBatch).where(
            ChargeBatch.id == batch_id,
            ChargeBatch.organization_id == organization_id,
        )
    )
    if batch is None:
        raise EntityNotFoundError("Aidat batch kaydı bulunamadı.")
    return batch


def post_charge_batch(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    batch_id: uuid.UUID,
) -> list[Charge]:
    batch = _scoped_batch(session, organization_id, batch_id)
    if batch.status is not ChargeBatchStatus.DRAFT:
        raise InvalidFinancialStateTransitionError(
            "Yalnız draft batch post edilebilir."
        )
    duplicate = session.scalar(
        select(ChargeBatch.id).where(
            ChargeBatch.building_id == batch.building_id,
            ChargeBatch.period_year == batch.period_year,
            ChargeBatch.period_month == batch.period_month,
            ChargeBatch.status == ChargeBatchStatus.POSTED,
            ChargeBatch.id != batch.id,
        )
    )
    if duplicate is not None:
        raise DuplicateChargeBatchError(
            "Bu bina ve dönem için posted aidat batch kaydı bulunmaktadır."
        )
    apartments = session.scalars(
        select(Apartment)
        .where(
            Apartment.organization_id == organization_id,
            Apartment.building_id == batch.building_id,
            Apartment.is_active.is_(True),
        )
        .order_by(Apartment.id)
    ).all()
    charges: list[Charge] = []
    try:
        with session.begin_nested():
            for apartment in apartments:
                charge = Charge(
                    organization_id=organization_id,
                    building_id=batch.building_id,
                    apartment_id=apartment.id,
                    charge_batch_id=batch.id,
                    charge_type=ChargeType.MONTHLY_DUE,
                    title=batch.title,
                    description=batch.description,
                    period_year=batch.period_year,
                    period_month=batch.period_month,
                    original_amount=batch.default_amount,
                    due_date=batch.due_date,
                    status=ChargeStatus.POSTED,
                    created_by_user_id=batch.created_by_user_id,
                )
                session.add(charge)
                charges.append(charge)
            batch.status = ChargeBatchStatus.POSTED
            session.flush()
    except IntegrityError as error:
        raise DuplicateChargeBatchError(
            "Batch posting benzersizlik kontrolüne takıldı."
        ) from error
    return charges


def cancel_charge_batch(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    batch_id: uuid.UUID,
    reason: str,
) -> ChargeBatch:
    batch = _scoped_batch(session, organization_id, batch_id)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ServiceValidationError("İptal nedeni zorunludur.")
    if batch.status is ChargeBatchStatus.CANCELLED:
        raise InvalidFinancialStateTransitionError("Batch zaten iptal edilmiştir.")
    charges = session.scalars(
        select(Charge).where(
            Charge.organization_id == organization_id,
            Charge.charge_batch_id == batch.id,
            Charge.status == ChargeStatus.POSTED,
        )
    ).all()
    for charge in charges:
        reverse_charge(
            session,
            organization_id=organization_id,
            charge_id=charge.id,
            reason=normalized_reason,
        )
    batch.status = ChargeBatchStatus.CANCELLED
    session.flush()
    return batch


def create_manual_charge(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    apartment_id: uuid.UUID,
    charge_type: ChargeType,
    title: str,
    description: str | None,
    amount: Decimal | str | int,
    due_date: date,
    created_by_user_id: uuid.UUID,
    period_year: int | None = None,
    period_month: int | None = None,
) -> Charge:
    require_financial_scope(
        session,
        organization_id=organization_id,
        building_id=building_id,
        apartment_id=apartment_id,
    )
    require_user(session, created_by_user_id)
    if period_month is not None and not 1 <= period_month <= 12:
        raise ServiceValidationError("Dönem ayı 1 ile 12 arasında olmalıdır.")
    charge = Charge(
        organization_id=organization_id,
        building_id=building_id,
        apartment_id=apartment_id,
        charge_type=charge_type,
        title=title.strip(),
        description=description or None,
        period_year=period_year,
        period_month=period_month,
        original_amount=money(amount),
        due_date=due_date,
        status=ChargeStatus.POSTED,
        created_by_user_id=created_by_user_id,
    )
    session.add(charge)
    session.flush()
    return charge


def get_charge_outstanding_amount(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    charge_id: uuid.UUID,
) -> Decimal:
    charge = session.scalar(
        select(Charge).where(
            Charge.id == charge_id,
            Charge.organization_id == organization_id,
        )
    )
    if charge is None:
        raise EntityNotFoundError("Borç kaydı bulunamadı.")
    if charge.status is not ChargeStatus.POSTED:
        return Decimal("0.00")
    allocated = session.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(
            PaymentAllocation.organization_id == organization_id,
            PaymentAllocation.charge_id == charge_id,
            Payment.status == PaymentStatus.POSTED,
        )
    )
    allocated_amount = allocated if allocated is not None else Decimal("0.00")
    return (charge.original_amount - allocated_amount).quantize(Decimal("0.01"))


def reverse_charge(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    charge_id: uuid.UUID,
    reason: str,
) -> Charge:
    charge = session.scalar(
        select(Charge).where(
            Charge.id == charge_id,
            Charge.organization_id == organization_id,
        )
    )
    if charge is None:
        raise EntityNotFoundError("Borç kaydı bulunamadı.")
    if charge.status is ChargeStatus.REVERSED:
        raise FinancialRecordAlreadyReversedError("Borç zaten ters çevrilmiştir.")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ServiceValidationError("Ters işlem nedeni zorunludur.")
    allocation_count = session.scalar(
        select(func.count(PaymentAllocation.id))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(
            PaymentAllocation.organization_id == organization_id,
            PaymentAllocation.charge_id == charge_id,
            Payment.status == PaymentStatus.POSTED,
        )
    )
    if allocation_count:
        raise ChargeHasAllocationsError(
            "Geçerli allocation bulunan borç ters çevrilemez."
        )
    charge.status = ChargeStatus.REVERSED
    charge.reversed_at = utc_now()
    charge.reversal_reason = normalized_reason
    session.flush()
    return charge

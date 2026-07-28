from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Charge,
    ChargeStatus,
    Payment,
    PaymentAllocation,
    PaymentMethod,
    PaymentStatus,
)
from app.models.base import utc_now
from app.services import (
    ChargeOverAllocationError,
    CrossTenantFinancialOperationError,
    DuplicateAllocationError,
    EntityNotFoundError,
    FinancialRecordAlreadyReversedError,
    InvalidFinancialStateTransitionError,
    PaymentOverAllocationError,
    ServiceValidationError,
    SessionLike,
)
from app.services.charges import get_charge_outstanding_amount
from app.services.financial_common import money, require_financial_scope
from app.services.tenancy import require_user


def record_payment(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    apartment_id: uuid.UUID,
    amount: Decimal | str | int,
    payment_date: date,
    payment_method: PaymentMethod,
    recorded_by_user_id: uuid.UUID,
    payer_user_id: uuid.UUID | None = None,
    reference: str | None = None,
    description: str | None = None,
) -> Payment:
    require_financial_scope(
        session,
        organization_id=organization_id,
        building_id=building_id,
        apartment_id=apartment_id,
    )
    require_user(session, recorded_by_user_id)
    if payer_user_id is not None:
        require_user(session, payer_user_id)
    payment = Payment(
        organization_id=organization_id,
        building_id=building_id,
        apartment_id=apartment_id,
        payer_user_id=payer_user_id,
        amount=money(amount),
        payment_date=payment_date,
        payment_method=payment_method,
        reference=reference or None,
        description=description or None,
        status=PaymentStatus.POSTED,
        recorded_by_user_id=recorded_by_user_id,
    )
    session.add(payment)
    session.flush()
    return payment


def _scoped_payment(
    session: SessionLike,
    organization_id: uuid.UUID,
    payment_id: uuid.UUID,
) -> Payment:
    payment = session.scalar(
        select(Payment).where(
            Payment.id == payment_id,
            Payment.organization_id == organization_id,
        )
    )
    if payment is None:
        raise EntityNotFoundError("Ödeme bulunamadı.")
    return payment


def get_payment_unallocated_amount(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    payment_id: uuid.UUID,
) -> Decimal:
    payment = _scoped_payment(session, organization_id, payment_id)
    if payment.status is not PaymentStatus.POSTED:
        return Decimal("0.00")
    allocated = session.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
            PaymentAllocation.organization_id == organization_id,
            PaymentAllocation.payment_id == payment_id,
        )
    )
    allocated_amount = allocated if allocated is not None else Decimal("0.00")
    return (payment.amount - allocated_amount).quantize(Decimal("0.01"))


def allocate_payment(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    payment_id: uuid.UUID,
    charge_id: uuid.UUID,
    amount: Decimal | str | int,
) -> PaymentAllocation:
    payment = _scoped_payment(session, organization_id, payment_id)
    charge = session.scalar(
        select(Charge).where(
            Charge.id == charge_id,
            Charge.organization_id == organization_id,
        )
    )
    if charge is None:
        raise EntityNotFoundError("Borç kaydı bulunamadı.")
    if payment.status is not PaymentStatus.POSTED:
        raise InvalidFinancialStateTransitionError(
            "Reversed ödeme allocate edilemez."
        )
    if charge.status is not ChargeStatus.POSTED:
        raise InvalidFinancialStateTransitionError(
            "Reversed borç allocate edilemez."
        )
    if (
        payment.apartment_id != charge.apartment_id
        or payment.building_id != charge.building_id
    ):
        raise CrossTenantFinancialOperationError(
            "Ödeme ve borç aynı daireye ait olmalıdır."
        )
    allocation_amount = money(amount)
    if allocation_amount > get_payment_unallocated_amount(
        session,
        organization_id=organization_id,
        payment_id=payment_id,
    ):
        raise PaymentOverAllocationError("Allocation ödeme tutarını aşamaz.")
    if allocation_amount > get_charge_outstanding_amount(
        session,
        organization_id=organization_id,
        charge_id=charge_id,
    ):
        raise ChargeOverAllocationError("Allocation borç tutarını aşamaz.")
    duplicate = session.scalar(
        select(PaymentAllocation.id).where(
            PaymentAllocation.payment_id == payment_id,
            PaymentAllocation.charge_id == charge_id,
        )
    )
    if duplicate is not None:
        raise DuplicateAllocationError(
            "Aynı ödeme-borç çifti için allocation zaten var."
        )
    allocation = PaymentAllocation(
        organization_id=organization_id,
        payment_id=payment_id,
        charge_id=charge_id,
        amount=allocation_amount,
    )
    session.add(allocation)
    try:
        session.flush()
    except IntegrityError as error:
        raise DuplicateAllocationError(
            "Aynı ödeme-borç çifti için allocation zaten var."
        ) from error
    return allocation


def auto_allocate_payment(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    payment_id: uuid.UUID,
) -> list[PaymentAllocation]:
    payment = _scoped_payment(session, organization_id, payment_id)
    if payment.status is not PaymentStatus.POSTED:
        raise InvalidFinancialStateTransitionError(
            "Reversed ödeme allocate edilemez."
        )
    charges = session.scalars(
        select(Charge)
        .where(
            Charge.organization_id == organization_id,
            Charge.apartment_id == payment.apartment_id,
            Charge.status == ChargeStatus.POSTED,
        )
        .order_by(Charge.due_date, Charge.created_at, Charge.id)
    ).all()
    allocations: list[PaymentAllocation] = []
    with session.begin_nested():
        for charge in charges:
            available = get_payment_unallocated_amount(
                session,
                organization_id=organization_id,
                payment_id=payment_id,
            )
            if available <= 0:
                break
            outstanding = get_charge_outstanding_amount(
                session,
                organization_id=organization_id,
                charge_id=charge.id,
            )
            if outstanding <= 0:
                continue
            allocations.append(
                allocate_payment(
                    session,
                    organization_id=organization_id,
                    payment_id=payment_id,
                    charge_id=charge.id,
                    amount=min(available, outstanding),
                )
            )
    return allocations


def reverse_payment(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    payment_id: uuid.UUID,
    reason: str,
) -> Payment:
    payment = _scoped_payment(session, organization_id, payment_id)
    if payment.status is PaymentStatus.REVERSED:
        raise FinancialRecordAlreadyReversedError("Ödeme zaten ters çevrilmiştir.")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ServiceValidationError("Ters işlem nedeni zorunludur.")
    payment.status = PaymentStatus.REVERSED
    payment.reversed_at = utc_now()
    payment.reversal_reason = normalized_reason
    session.flush()
    return payment

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select

from app.models import (
    Charge,
    ChargeStatus,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from app.services import SessionLike
from app.services.financial_common import require_financial_scope


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


@dataclass(frozen=True, slots=True)
class ApartmentBalance:
    total_charges: Decimal
    total_payments: Decimal
    total_allocated: Decimal
    total_outstanding: Decimal


def get_apartment_balance(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> ApartmentBalance:
    require_financial_scope(
        session,
        organization_id=organization_id,
        building_id=building_id,
        apartment_id=apartment_id,
    )
    total_charges = _decimal(
        session.scalar(
            select(func.coalesce(func.sum(Charge.original_amount), 0)).where(
                Charge.organization_id == organization_id,
                Charge.apartment_id == apartment_id,
                Charge.status == ChargeStatus.POSTED,
            )
        )
    )
    total_payments = _decimal(
        session.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.organization_id == organization_id,
                Payment.apartment_id == apartment_id,
                Payment.status == PaymentStatus.POSTED,
            )
        )
    )
    total_allocated = _decimal(
        session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .join(Charge, Charge.id == PaymentAllocation.charge_id)
            .where(
                PaymentAllocation.organization_id == organization_id,
                Payment.apartment_id == apartment_id,
                Payment.status == PaymentStatus.POSTED,
                Charge.status == ChargeStatus.POSTED,
            )
        )
    )
    return ApartmentBalance(
        total_charges=total_charges,
        total_payments=total_payments,
        total_allocated=total_allocated,
        total_outstanding=(total_charges - total_allocated).quantize(
            Decimal("0.01")
        ),
    )

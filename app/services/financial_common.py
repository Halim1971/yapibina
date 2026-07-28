from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.models import Apartment, Building
from app.services import (
    CrossTenantFinancialOperationError,
    EntityNotFoundError,
    InvalidAmountError,
    SessionLike,
)

MONEY_QUANTUM = Decimal("0.01")


def money(value: Decimal | str | int) -> Decimal:
    try:
        amount = Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as error:
        raise InvalidAmountError("Geçerli bir para tutarı gereklidir.") from error
    if not amount.is_finite() or amount <= 0:
        raise InvalidAmountError("Tutar sıfırdan büyük olmalıdır.")
    return amount


def require_financial_scope(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    building_id: uuid.UUID,
    apartment_id: uuid.UUID,
) -> tuple[Building, Apartment]:
    building = session.get(Building, building_id)
    apartment = session.get(Apartment, apartment_id)
    if building is None or apartment is None:
        raise EntityNotFoundError("Bina veya daire bulunamadı.")
    if (
        building.organization_id != organization_id
        or apartment.organization_id != organization_id
        or apartment.building_id != building_id
    ):
        raise CrossTenantFinancialOperationError(
            "Finansal kaynaklar aynı tenant ve bina kapsamında olmalıdır."
        )
    return building, apartment

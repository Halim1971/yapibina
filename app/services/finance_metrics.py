from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement

from app.models import Charge

MONEY_ZERO = Decimal("0.00")


def money_decimal(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def month_range(reference: date) -> tuple[date, date]:
    start = reference.replace(day=1)
    if start.month == 12:
        return start, date(start.year + 1, 1, 1)
    return start, date(start.year, start.month + 1, 1)


def local_today(timezone_name: str) -> date:
    return datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_name)).date()


def period_charge_filter(start: date, end: date) -> ColumnElement[bool]:
    return or_(
        and_(
            Charge.period_year == start.year,
            Charge.period_month == start.month,
        ),
        and_(
            Charge.period_year.is_(None),
            Charge.period_month.is_(None),
            Charge.due_date >= start,
            Charge.due_date < end,
        ),
    )

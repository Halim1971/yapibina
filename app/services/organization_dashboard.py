from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.imports.models import ImportRun, ImportRunStatus
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
from app.services import SessionLike

MONEY_ZERO = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class ImportSummary:
    id: uuid.UUID
    finished_at: datetime
    inserted: int
    updated: int
    skipped: int
    deferred: int


@dataclass(frozen=True, slots=True)
class BuildingSummary:
    id: uuid.UUID
    name: str
    apartment_count: int
    active_resident_count: int
    outstanding_debt: Decimal
    current_month_payments: Decimal


@dataclass(frozen=True, slots=True)
class FinancialMovement:
    id: uuid.UUID
    movement_date: date
    building_name: str
    apartment_label: str
    description: str
    amount: Decimal
    kind: str


@dataclass(frozen=True, slots=True)
class OrganizationDashboard:
    building_count: int
    apartment_count: int
    active_resident_count: int
    outstanding_debt: Decimal
    current_month_payments: Decimal
    current_month_charges: Decimal
    collection_rate: Decimal | None
    successful_import: ImportSummary | None
    latest_import_failed: bool
    buildings: tuple[BuildingSummary, ...]
    movements: tuple[FinancialMovement, ...]
    period_label: str


def money_decimal(value: object) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def month_range(reference: date) -> tuple[date, date]:
    start = reference.replace(day=1)
    if start.month == 12:
        return start, date(start.year + 1, 1, 1)
    return start, date(start.year, start.month + 1, 1)


def local_today(timezone_name: str) -> date:
    return datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_name)).date()


def _period_charge_filter(start: date, end: date) -> ColumnElement[bool]:
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


def _integer_map(rows: list[tuple[uuid.UUID, int]]) -> dict[uuid.UUID, int]:
    return {key: int(value) for key, value in rows}


def _money_map(rows: list[tuple[uuid.UUID, object]]) -> dict[uuid.UUID, Decimal]:
    return {key: money_decimal(value) for key, value in rows}


def _import_summary(
    run: ImportRun | None,
    timezone_name: str,
) -> ImportSummary | None:
    if run is None or run.finished_at is None:
        return None
    finished_at = run.finished_at
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)
    return ImportSummary(
        id=run.id,
        finished_at=finished_at.astimezone(ZoneInfo(timezone_name)),
        inserted=run.inserted_count,
        updated=run.updated_count,
        skipped=run.skipped_count,
        deferred=run.expense_count + run.announcement_count,
    )


def _building_summaries(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    now: datetime,
    month_start: date,
    month_end: date,
) -> tuple[tuple[BuildingSummary, ...], int, int, Decimal, Decimal]:
    building_rows = session.execute(
        select(Building, func.count(Building.id).over().label("total_count"))
        .where(Building.organization_id == organization_id)
        .order_by(Building.name, Building.id)
        .limit(10)
    ).all()
    buildings = [row.Building for row in building_rows]
    building_count = int(building_rows[0].total_count) if building_rows else 0
    apartment_rows = list(
        session.execute(
            select(Apartment.building_id, func.count(Apartment.id))
            .where(Apartment.organization_id == organization_id)
            .group_by(Apartment.building_id)
        ).tuples()
    )
    apartment_counts = _integer_map(apartment_rows)
    apartment_count = sum(apartment_counts.values())
    resident_counts = _integer_map(
        list(
            session.execute(
                select(
                    Apartment.building_id,
                    func.count(func.distinct(ApartmentMembership.user_id)),
                )
                .join(
                    ApartmentMembership,
                    and_(
                        ApartmentMembership.apartment_id == Apartment.id,
                        ApartmentMembership.organization_id == organization_id,
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
                .join(Building, Building.id == Apartment.building_id)
                .where(
                    Apartment.organization_id == organization_id,
                    Apartment.is_active.is_(True),
                    Building.is_active.is_(True),
                    User.status == UserStatus.ACTIVE,
                    ApartmentMembership.is_active.is_(True),
                    ApartmentMembership.starts_at <= now,
                    or_(
                        ApartmentMembership.ends_at.is_(None),
                        ApartmentMembership.ends_at >= now,
                    ),
                    OrganizationMembership.is_active.is_(True),
                    OrganizationMembership.starts_at <= now,
                    or_(
                        OrganizationMembership.ends_at.is_(None),
                        OrganizationMembership.ends_at >= now,
                    ),
                )
                .group_by(Apartment.building_id)
            ).tuples()
        )
    )
    charge_totals = _money_map(
        list(
            session.execute(
                select(Charge.building_id, func.sum(Charge.original_amount))
                .where(
                    Charge.organization_id == organization_id,
                    Charge.status == ChargeStatus.POSTED,
                )
                .group_by(Charge.building_id)
            ).tuples()
        )
    )
    allocation_totals = _money_map(
        list(
            session.execute(
                select(Charge.building_id, func.sum(PaymentAllocation.amount))
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
                .group_by(Charge.building_id)
            ).tuples()
        )
    )
    monthly_payments = _money_map(
        list(
            session.execute(
                select(Payment.building_id, func.sum(Payment.amount))
                .where(
                    Payment.organization_id == organization_id,
                    Payment.status == PaymentStatus.POSTED,
                    Payment.payment_date >= month_start,
                    Payment.payment_date < month_end,
                )
                .group_by(Payment.building_id)
            ).tuples()
        )
    )
    items = tuple(
        BuildingSummary(
            id=building.id,
            name=building.name,
            apartment_count=apartment_counts.get(building.id, 0),
            active_resident_count=resident_counts.get(building.id, 0),
            outstanding_debt=max(
                charge_totals.get(building.id, MONEY_ZERO)
                - allocation_totals.get(building.id, MONEY_ZERO),
                MONEY_ZERO,
            ),
            current_month_payments=monthly_payments.get(
                building.id,
                MONEY_ZERO,
            ),
        )
        for building in buildings
    )
    return (
        items,
        building_count,
        apartment_count,
        max(
            sum(charge_totals.values(), MONEY_ZERO)
            - sum(allocation_totals.values(), MONEY_ZERO),
            MONEY_ZERO,
        ),
        sum(monthly_payments.values(), MONEY_ZERO),
    )


def _active_resident_count(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    now: datetime,
) -> int:
    return int(
        session.scalar(
            select(func.count(func.distinct(ApartmentMembership.user_id)))
            .join(
                Apartment,
                and_(
                    Apartment.id == ApartmentMembership.apartment_id,
                    Apartment.organization_id == organization_id,
                ),
            )
            .join(Building, Building.id == Apartment.building_id)
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
        )
        or 0
    )


def _recent_movements(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
) -> tuple[FinancialMovement, ...]:
    charges = session.execute(
        select(
            Charge.id,
            Charge.due_date,
            Building.name,
            Apartment.unit_code,
            Apartment.number,
            Charge.title,
            Charge.original_amount,
        )
        .join(
            Building,
            and_(
                Building.id == Charge.building_id,
                Building.organization_id == organization_id,
            ),
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
            Charge.status == ChargeStatus.POSTED,
        )
        .order_by(Charge.due_date.desc(), Charge.created_at.desc(), Charge.id.desc())
        .limit(10)
    ).all()
    payments = session.execute(
        select(
            Payment.id,
            Payment.payment_date,
            Building.name,
            Apartment.unit_code,
            Apartment.number,
            Payment.description,
            Payment.reference,
            Payment.amount,
        )
        .join(
            Building,
            and_(
                Building.id == Payment.building_id,
                Building.organization_id == organization_id,
            ),
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
        FinancialMovement(
            id=row.id,
            movement_date=row.due_date,
            building_name=row.name,
            apartment_label=row.unit_code or row.number,
            description=row.title,
            amount=money_decimal(row.original_amount),
            kind="Borç",
        )
        for row in charges
    ]
    movements.extend(
        FinancialMovement(
            id=row.id,
            movement_date=row.payment_date,
            building_name=row.name,
            apartment_label=row.unit_code or row.number,
            description=row.description or row.reference or "Ödeme",
            amount=money_decimal(row.amount),
            kind="Ödeme",
        )
        for row in payments
    )
    movements.sort(
        key=lambda item: (
            item.movement_date,
            item.kind == "Ödeme",
            str(item.id),
        ),
        reverse=True,
    )
    return tuple(movements[:10])


def get_organization_dashboard(
    session: SessionLike,
    *,
    organization_id: uuid.UUID,
    timezone_name: str,
    reference_date: date | None = None,
) -> OrganizationDashboard:
    today = reference_date or local_today(timezone_name)
    month_start, month_end = month_range(today)
    now = datetime.now(timezone.utc)
    (
        buildings,
        building_count,
        apartment_count,
        outstanding_debt,
        current_month_payments,
    ) = _building_summaries(
        session,
        organization_id=organization_id,
        now=now,
        month_start=month_start,
        month_end=month_end,
    )
    current_month_charges = money_decimal(
        session.execute(
            select(func.coalesce(func.sum(Charge.original_amount), 0)).where(
                Charge.organization_id == organization_id,
                Charge.status == ChargeStatus.POSTED,
                _period_charge_filter(month_start, month_end),
            )
        )
        .scalar_one()
    )
    collection_rate = (
        (
            current_month_payments
            / current_month_charges
            * Decimal("100")
        ).quantize(Decimal("0.01"))
        if current_month_charges > 0
        else None
    )
    latest_success = session.scalar(
        select(ImportRun)
        .where(
            ImportRun.organization_id == organization_id,
            ImportRun.status == ImportRunStatus.COMPLETED,
        )
        .order_by(ImportRun.finished_at.desc(), ImportRun.id.desc())
        .limit(1)
    )
    latest_run = session.scalar(
        select(ImportRun)
        .where(ImportRun.organization_id == organization_id)
        .order_by(ImportRun.started_at.desc(), ImportRun.id.desc())
        .limit(1)
    )
    return OrganizationDashboard(
        building_count=building_count,
        apartment_count=apartment_count,
        active_resident_count=_active_resident_count(
            session,
            organization_id=organization_id,
            now=now,
        ),
        outstanding_debt=outstanding_debt,
        current_month_payments=current_month_payments,
        current_month_charges=current_month_charges,
        collection_rate=collection_rate,
        successful_import=_import_summary(latest_success, timezone_name),
        latest_import_failed=bool(
            latest_run is not None
            and latest_run.status == ImportRunStatus.FAILED
        ),
        buildings=buildings,
        movements=_recent_movements(
            session,
            organization_id=organization_id,
        ),
        period_label=today.strftime("%m/%Y"),
    )

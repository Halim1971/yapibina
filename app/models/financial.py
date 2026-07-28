from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base, db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utc_now
from app.models.enums import (
    ChargeBatchStatus,
    ChargeStatus,
    ChargeType,
    PaymentMethod,
    PaymentStatus,
)

if TYPE_CHECKING:
    from app.models.apartment import Apartment
    from app.models.building import Building
    from app.models.user import User

MONEY_TYPE = Numeric(14, 2)


def _enum_type(enum: type, name: str) -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        enum,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
        name=name,
    )


class ChargeBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "charge_batches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "building_id"],
            ["buildings.organization_id", "buildings.id"],
            ondelete="RESTRICT",
            name="fk_charge_batches_org_building",
        ),
        CheckConstraint(
            "period_month BETWEEN 1 AND 12",
            name="ck_charge_batches_period_month",
        ),
        CheckConstraint(
            "default_amount > 0",
            name="ck_charge_batches_positive_amount",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_charge_batches_org_id",
        ),
        Index(
            "uq_charge_batches_posted_period",
            "building_id",
            "period_year",
            "period_month",
            unique=True,
            postgresql_where=text("status = 'posted'"),
            sqlite_where=text("status = 'posted'"),
        ),
        Index(
            "ix_charge_batches_org_building_period",
            "organization_id",
            "building_id",
            "period_year",
            "period_month",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    building_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    period_year: Mapped[int] = mapped_column(nullable=False)
    period_month: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    default_amount: Mapped[Decimal] = mapped_column(MONEY_TYPE, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[ChargeBatchStatus] = mapped_column(
        _enum_type(ChargeBatchStatus, "charge_batch_status"),
        default=ChargeBatchStatus.DRAFT,
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    building: Mapped[Building] = relationship(overlaps="charges")
    created_by: Mapped[User] = relationship()
    charges: Mapped[list[Charge]] = relationship(back_populates="charge_batch")


class Charge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "charges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "building_id"],
            ["buildings.organization_id", "buildings.id"],
            ondelete="RESTRICT",
            name="fk_charges_org_building",
        ),
        ForeignKeyConstraint(
            ["organization_id", "apartment_id"],
            ["apartments.organization_id", "apartments.id"],
            ondelete="RESTRICT",
            name="fk_charges_org_apartment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "charge_batch_id"],
            ["charge_batches.organization_id", "charge_batches.id"],
            ondelete="RESTRICT",
            name="fk_charges_org_batch",
        ),
        CheckConstraint("original_amount > 0", name="ck_charges_positive_amount"),
        CheckConstraint(
            "period_month IS NULL OR period_month BETWEEN 1 AND 12",
            name="ck_charges_period_month",
        ),
        UniqueConstraint("organization_id", "id", name="uq_charges_org_id"),
        Index(
            "ix_charges_org_apartment_status_due",
            "organization_id",
            "apartment_id",
            "status",
            "due_date",
        ),
        Index("ix_charges_charge_batch_id", "charge_batch_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    building_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    apartment_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    charge_batch_id: Mapped[uuid.UUID | None] = mapped_column(db.Uuid)
    charge_type: Mapped[ChargeType] = mapped_column(
        _enum_type(ChargeType, "charge_type"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    period_year: Mapped[int | None]
    period_month: Mapped[int | None]
    original_amount: Mapped[Decimal] = mapped_column(MONEY_TYPE, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[ChargeStatus] = mapped_column(
        _enum_type(ChargeStatus, "charge_status"),
        default=ChargeStatus.POSTED,
        nullable=False,
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    building: Mapped[Building] = relationship(overlaps="charges")
    apartment: Mapped[Apartment] = relationship(overlaps="building,charges")
    charge_batch: Mapped[ChargeBatch | None] = relationship(
        back_populates="charges",
        overlaps="apartment,building",
    )
    created_by: Mapped[User] = relationship()
    allocations: Mapped[list[PaymentAllocation]] = relationship(
        back_populates="charge"
    )


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "building_id"],
            ["buildings.organization_id", "buildings.id"],
            ondelete="RESTRICT",
            name="fk_payments_org_building",
        ),
        ForeignKeyConstraint(
            ["organization_id", "apartment_id"],
            ["apartments.organization_id", "apartments.id"],
            ondelete="RESTRICT",
            name="fk_payments_org_apartment",
        ),
        CheckConstraint("amount > 0", name="ck_payments_positive_amount"),
        UniqueConstraint("organization_id", "id", name="uq_payments_org_id"),
        Index(
            "ix_payments_org_apartment_status_date",
            "organization_id",
            "apartment_id",
            "status",
            "payment_date",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    building_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    apartment_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    payer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        db.Uuid,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
    )
    amount: Mapped[Decimal] = mapped_column(MONEY_TYPE, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        _enum_type(PaymentMethod, "payment_method"),
        nullable=False,
    )
    reference: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[PaymentStatus] = mapped_column(
        _enum_type(PaymentStatus, "payment_status"),
        default=PaymentStatus.POSTED,
        nullable=False,
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversal_reason: Mapped[str | None] = mapped_column(String(500))
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    building: Mapped[Building] = relationship()
    apartment: Mapped[Apartment] = relationship(overlaps="building")
    payer: Mapped[User | None] = relationship(foreign_keys=[payer_user_id])
    recorded_by: Mapped[User] = relationship(foreign_keys=[recorded_by_user_id])
    allocations: Mapped[list[PaymentAllocation]] = relationship(
        back_populates="payment",
        overlaps="allocations",
    )


class PaymentAllocation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "payment_id"],
            ["payments.organization_id", "payments.id"],
            ondelete="RESTRICT",
            name="fk_allocations_org_payment",
        ),
        ForeignKeyConstraint(
            ["organization_id", "charge_id"],
            ["charges.organization_id", "charges.id"],
            ondelete="RESTRICT",
            name="fk_allocations_org_charge",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_payment_allocations_positive_amount",
        ),
        UniqueConstraint(
            "payment_id",
            "charge_id",
            name="uq_payment_allocations_payment_charge",
        ),
        Index(
            "ix_payment_allocations_org_payment",
            "organization_id",
            "payment_id",
        ),
        Index(
            "ix_payment_allocations_org_charge",
            "organization_id",
            "charge_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    payment_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    charge_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY_TYPE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    payment: Mapped[Payment] = relationship(
        back_populates="allocations",
        overlaps="allocations",
    )
    charge: Mapped[Charge] = relationship(
        back_populates="allocations",
        overlaps="allocations,payment",
    )


def _protect_posted_financial_fields(
    target: Charge | Payment,
    field_names: tuple[str, ...],
) -> None:
    state = cast(Any, inspect(target))
    status_history = state.attrs.status.history
    prior_status = status_history.deleted[0] if status_history.deleted else target.status
    posted_status = (
        ChargeStatus.POSTED if isinstance(target, Charge) else PaymentStatus.POSTED
    )
    if prior_status is not posted_status:
        return
    if any(state.attrs[field].history.has_changes() for field in field_names):
        raise ValueError("Posted financial fields are immutable.")


@event.listens_for(Charge, "before_update")
def _protect_charge_fields(_mapper: object, _connection: object, target: Charge) -> None:
    _protect_posted_financial_fields(
        target,
        (
            "organization_id",
            "building_id",
            "apartment_id",
            "charge_batch_id",
            "original_amount",
            "due_date",
            "charge_type",
        ),
    )


@event.listens_for(Payment, "before_update")
def _protect_payment_fields(
    _mapper: object,
    _connection: object,
    target: Payment,
) -> None:
    _protect_posted_financial_fields(
        target,
        (
            "organization_id",
            "building_id",
            "apartment_id",
            "amount",
            "payment_date",
            "payment_method",
        ),
    )

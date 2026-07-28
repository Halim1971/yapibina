from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base, db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, as_utc, utc_now
from app.models.enums import ApartmentMembershipRole

if TYPE_CHECKING:
    from app.models.building import Building
    from app.models.user import User


class Apartment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "apartments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "building_id"],
            ["buildings.organization_id", "buildings.id"],
            ondelete="RESTRICT",
            name="fk_apartments_org_building",
        ),
        UniqueConstraint(
            "building_id",
            "unit_code",
            name="uq_apartments_building_unit_code",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_apartments_org_id",
        ),
        Index("ix_apartments_org_building", "organization_id", "building_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    building_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    number: Mapped[str] = mapped_column(String(30), nullable=False)
    floor: Mapped[str | None] = mapped_column(String(30))
    block: Mapped[str | None] = mapped_column(String(30))
    unit_code: Mapped[str | None] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    building: Mapped[Building] = relationship(back_populates="apartments")
    memberships: Mapped[list[ApartmentMembership]] = relationship(
        back_populates="apartment",
        passive_deletes=True,
    )


class ApartmentMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "apartment_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "apartment_id"],
            ["apartments.organization_id", "apartments.id"],
            ondelete="RESTRICT",
            name="fk_apartment_memberships_org_apartment",
        ),
        CheckConstraint(
            "ends_at IS NULL OR ends_at >= starts_at",
            name="ck_apartment_memberships_valid_dates",
        ),
        Index(
            "ix_apartment_memberships_org_user_active",
            "organization_id",
            "user_id",
            "is_active",
        ),
        Index(
            "ix_apartment_memberships_apartment_period",
            "apartment_id",
            "starts_at",
            "ends_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    apartment_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[ApartmentMembershipRole] = mapped_column(
        SQLAlchemyEnum(
            ApartmentMembershipRole,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            name="apartment_membership_role",
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    apartment: Mapped[Apartment] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="apartment_memberships")

    def is_effective(self, at: datetime | None = None) -> bool:
        reference = at or utc_now()
        return bool(
            self.is_active
            and as_utc(self.starts_at) <= as_utc(reference)
            and (self.ends_at is None or as_utc(self.ends_at) >= as_utc(reference))
        )

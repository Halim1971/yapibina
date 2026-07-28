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
    text,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base, db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, as_utc, utc_now
from app.models.enums import BuildingMembershipRole

if TYPE_CHECKING:
    from app.models.apartment import Apartment
    from app.models.organization import Organization
    from app.models.user import User


class Building(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "buildings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_buildings_org_code",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_buildings_org_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))
    address_line: Mapped[str | None] = mapped_column(String(300))
    district: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    organization: Mapped[Organization] = relationship(back_populates="buildings")
    memberships: Mapped[list[BuildingMembership]] = relationship(
        back_populates="building",
        passive_deletes=True,
    )
    apartments: Mapped[list[Apartment]] = relationship(
        back_populates="building",
        passive_deletes=True,
    )


class BuildingMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "building_memberships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "building_id"],
            ["buildings.organization_id", "buildings.id"],
            ondelete="RESTRICT",
            name="fk_building_memberships_org_building",
        ),
        CheckConstraint(
            "ends_at IS NULL OR ends_at >= starts_at",
            name="ck_building_memberships_valid_dates",
        ),
        Index(
            "uq_building_memberships_active_user",
            "building_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
        Index(
            "ix_building_memberships_org_user",
            "organization_id",
            "user_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    building_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[BuildingMembershipRole] = mapped_column(
        SQLAlchemyEnum(
            BuildingMembershipRole,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            name="building_membership_role",
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

    building: Mapped[Building] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="building_memberships")

    def is_effective(self, at: datetime | None = None) -> bool:
        reference = at or utc_now()
        return bool(
            self.is_active
            and as_utc(self.starts_at) <= as_utc(reference)
            and (self.ends_at is None or as_utc(self.ends_at) >= as_utc(reference))
        )

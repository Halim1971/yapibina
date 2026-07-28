from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base, db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, as_utc, utc_now
from app.models.enums import OrganizationMembershipRole

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class OrganizationMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_memberships_org_user",
        ),
        CheckConstraint(
            "ends_at IS NULL OR ends_at >= starts_at",
            name="ck_organization_memberships_valid_dates",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    role: Mapped[OrganizationMembershipRole] = mapped_column(
        SQLAlchemyEnum(
            OrganizationMembershipRole,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            name="organization_membership_role",
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

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="organization_memberships")

    def is_effective(self, at: datetime | None = None) -> bool:
        reference = at or utc_now()
        return bool(
            self.is_active
            and as_utc(self.starts_at) <= as_utc(reference)
            and (self.ends_at is None or as_utc(self.ends_at) >= as_utc(reference))
        )

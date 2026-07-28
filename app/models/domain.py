from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, String, text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import Base, db
from app.models.base import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    normalize_hostname_value,
)
from app.models.enums import DomainState, DomainType

if TYPE_CHECKING:
    from app.models.organization import Organization


class OrganizationDomain(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_domains"
    __table_args__ = (
        Index(
            "uq_organization_domains_primary_per_org",
            "organization_id",
            unique=True,
            postgresql_where=text("is_primary"),
            sqlite_where=text("is_primary = 1"),
        ),
        Index("ix_organization_domains_org_state", "organization_id", "state"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    hostname: Mapped[str] = mapped_column(String(253), unique=True, nullable=False)
    domain_type: Mapped[DomainType] = mapped_column(
        SQLAlchemyEnum(
            DomainType,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            name="domain_type",
        ),
        nullable=False,
    )
    state: Mapped[DomainState] = mapped_column(
        SQLAlchemyEnum(
            DomainState,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            name="domain_state",
        ),
        default=DomainState.PENDING,
        nullable=False,
    )
    verification_token: Mapped[str | None] = mapped_column(String(255))
    verified_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    ssl_issued_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(500))

    organization: Mapped[Organization] = relationship(back_populates="domains")

    @validates("hostname")
    def validate_hostname(self, _: str, value: str) -> str:
        return normalize_hostname_value(value)

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import Base, db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, normalize_slug
from app.models.enums import OrganizationStatus

if TYPE_CHECKING:
    from app.models.building import Building
    from app.models.domain import OrganizationDomain
    from app.models.membership import OrganizationMembership


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(240))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    status: Mapped[OrganizationStatus] = mapped_column(
        SQLAlchemyEnum(
            OrganizationStatus,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            name="organization_status",
        ),
        default=OrganizationStatus.PENDING,
        nullable=False,
    )
    support_email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(500))

    branding: Mapped[OrganizationBranding | None] = relationship(
        back_populates="organization",
        uselist=False,
        passive_deletes=True,
    )
    domains: Mapped[list[OrganizationDomain]] = relationship(
        back_populates="organization",
        passive_deletes=True,
    )
    memberships: Mapped[list[OrganizationMembership]] = relationship(
        back_populates="organization",
        passive_deletes=True,
    )
    buildings: Mapped[list[Building]] = relationship(
        back_populates="organization",
        passive_deletes=True,
    )

    @validates("slug")
    def validate_slug(self, _: str, value: str) -> str:
        return normalize_slug(value)


class OrganizationBranding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_brandings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("organizations.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    company_display_name: Mapped[str | None] = mapped_column(String(160))
    logo_storage_key: Mapped[str | None] = mapped_column(String(500))
    small_logo_storage_key: Mapped[str | None] = mapped_column(String(500))
    favicon_storage_key: Mapped[str | None] = mapped_column(String(500))
    primary_color: Mapped[str | None] = mapped_column(String(7))
    secondary_color: Mapped[str | None] = mapped_column(String(7))
    surface_color: Mapped[str | None] = mapped_column(String(7))
    panel_title: Mapped[str | None] = mapped_column(String(120))
    login_message: Mapped[str | None] = mapped_column(String(500))
    white_label_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    organization: Mapped[Organization] = relationship(back_populates="branding")

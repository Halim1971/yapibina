from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base, db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AnnouncementAudienceScope, AnnouncementStatus

if TYPE_CHECKING:
    from app.models.building import Building
    from app.models.organization import Organization
    from app.models.user import User


class Announcement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_announcements_org_id"
        ),
        CheckConstraint(
            "status != 'published' OR published_at IS NOT NULL",
            name="ck_announcements_published_at_required",
        ),
        CheckConstraint(
            "expires_at IS NULL OR published_at IS NULL OR expires_at > published_at",
            name="ck_announcements_valid_visibility_period",
        ),
        Index("ix_announcements_org_status", "organization_id", "status"),
        Index("ix_announcements_org_published", "organization_id", "published_at"),
        Index("ix_announcements_org_expires", "organization_id", "expires_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AnnouncementStatus] = mapped_column(
        SQLAlchemyEnum(
            AnnouncementStatus,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            name="announcement_status",
        ),
        default=AnnouncementStatus.DRAFT,
        nullable=False,
    )
    audience_scope: Mapped[AnnouncementAudienceScope] = mapped_column(
        SQLAlchemyEnum(
            AnnouncementAudienceScope,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            name="announcement_audience_scope",
        ),
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization] = relationship()
    creator: Mapped[User] = relationship()
    building_targets: Mapped[list[AnnouncementBuilding]] = relationship(
        back_populates="announcement",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AnnouncementBuilding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "announcement_buildings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "announcement_id"],
            ["announcements.organization_id", "announcements.id"],
            ondelete="CASCADE",
            name="fk_announcement_buildings_org_announcement",
        ),
        ForeignKeyConstraint(
            ["organization_id", "building_id"],
            ["buildings.organization_id", "buildings.id"],
            ondelete="RESTRICT",
            name="fk_announcement_buildings_org_building",
        ),
        UniqueConstraint(
            "announcement_id",
            "building_id",
            name="uq_announcement_buildings_announcement_building",
        ),
        Index(
            "ix_announcement_buildings_org_building",
            "organization_id",
            "building_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid, nullable=False, index=True
    )
    building_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)

    announcement: Mapped[Announcement] = relationship(
        back_populates="building_targets"
    )
    building: Mapped[Building] = relationship(
        overlaps="announcement,building_targets"
    )

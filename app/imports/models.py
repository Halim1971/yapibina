from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base, db
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class ImportRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "import_runs"
    __table_args__ = (
        Index(
            "uq_import_runs_org_running",
            "organization_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
        Index(
            "uq_import_runs_completed_fingerprint",
            "organization_id",
            "source_system",
            "package_fingerprint",
            unique=True,
            postgresql_where=text("status = 'completed'"),
            sqlite_where=text("status = 'completed'"),
        ),
        Index(
            "ix_import_runs_org_started",
            "organization_id",
            "started_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(60), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    package_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ImportRunStatus] = mapped_column(
        SQLAlchemyEnum(
            ImportRunStatus,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
            name="import_run_status",
        ),
        default=ImportRunStatus.PENDING,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        db.Uuid,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
    )
    site_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resident_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    charge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expense_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    announcement_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text)
    import_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        db.JSON,
    )


class ExternalRecordMap(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "external_record_maps"
    __table_args__ = (
        db.UniqueConstraint(
            "organization_id",
            "source_system",
            "entity_type",
            "source_key",
            name="uq_external_record_maps_source_key",
        ),
        Index(
            "ix_external_record_maps_internal",
            "organization_id",
            "entity_type",
            "internal_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    internal_id: Mapped[uuid.UUID] = mapped_column(db.Uuid, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        db.Uuid,
        db.ForeignKey("import_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)

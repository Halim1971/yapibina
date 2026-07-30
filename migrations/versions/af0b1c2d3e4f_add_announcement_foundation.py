"""add announcement foundation

Revision ID: af0b1c2d3e4f
Revises: 8d41e3b720f2
Create Date: 2026-07-30 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "af0b1c2d3e4f"
down_revision: str | None = "8d41e3b720f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "published",
                "archived",
                name="announcement_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "audience_scope",
            sa.Enum(
                "organization",
                "buildings",
                name="announcement_audience_scope",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_announcements_created_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_announcements_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status != 'published' OR published_at IS NOT NULL",
            name="ck_announcements_published_at_required",
        ),
        sa.CheckConstraint(
            "expires_at IS NULL OR published_at IS NULL OR expires_at > published_at",
            name="ck_announcements_valid_visibility_period",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcements")),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_announcements_org_id"
        ),
    )
    op.create_index(
        "ix_announcements_org_expires",
        "announcements",
        ["organization_id", "expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_announcements_org_published",
        "announcements",
        ["organization_id", "published_at"],
        unique=False,
    )
    op.create_index(
        "ix_announcements_org_status",
        "announcements",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_table(
        "announcement_buildings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("announcement_id", sa.Uuid(), nullable=False),
        sa.Column("building_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "announcement_id"],
            ["announcements.organization_id", "announcements.id"],
            name="fk_announcement_buildings_org_announcement",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "building_id"],
            ["buildings.organization_id", "buildings.id"],
            name="fk_announcement_buildings_org_building",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcement_buildings")),
        sa.UniqueConstraint(
            "announcement_id",
            "building_id",
            name="uq_announcement_buildings_announcement_building",
        ),
    )
    op.create_index(
        op.f("ix_announcement_buildings_announcement_id"),
        "announcement_buildings",
        ["announcement_id"],
        unique=False,
    )
    op.create_index(
        "ix_announcement_buildings_org_building",
        "announcement_buildings",
        ["organization_id", "building_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_announcement_buildings_org_building",
        table_name="announcement_buildings",
    )
    op.drop_index(
        op.f("ix_announcement_buildings_announcement_id"),
        table_name="announcement_buildings",
    )
    op.drop_table("announcement_buildings")
    op.drop_index("ix_announcements_org_status", table_name="announcements")
    op.drop_index("ix_announcements_org_published", table_name="announcements")
    op.drop_index("ix_announcements_org_expires", table_name="announcements")
    op.drop_table("announcements")

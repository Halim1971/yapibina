"""add announcement read receipts

Revision ID: b1c2d3e4f5a6
Revises: af0b1c2d3e4f
Create Date: 2026-07-30 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "af0b1c2d3e4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "announcement_reads",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("announcement_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "announcement_id"],
            ["announcements.organization_id", "announcements.id"],
            name="fk_announcement_reads_org_announcement",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_announcement_reads_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_announcement_reads")),
        sa.UniqueConstraint(
            "announcement_id",
            "user_id",
            name="uq_announcement_reads_announcement_user",
        ),
    )
    op.create_index(
        "ix_announcement_reads_org_announcement",
        "announcement_reads",
        ["organization_id", "announcement_id"],
        unique=False,
    )
    op.create_index(
        "ix_announcement_reads_org_user",
        "announcement_reads",
        ["organization_id", "user_id"],
        unique=False,
    )
    op.create_index(
        "ix_announcement_reads_read_at",
        "announcement_reads",
        ["read_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_announcement_reads_read_at", table_name="announcement_reads")
    op.drop_index("ix_announcement_reads_org_user", table_name="announcement_reads")
    op.drop_index(
        "ix_announcement_reads_org_announcement",
        table_name="announcement_reads",
    )
    op.drop_table("announcement_reads")

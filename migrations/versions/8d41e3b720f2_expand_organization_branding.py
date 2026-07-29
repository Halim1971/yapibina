"""expand organization branding

Revision ID: 8d41e3b720f2
Revises: e5bcf7b6291d
Create Date: 2026-07-29 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8d41e3b720f2"
down_revision: str | None = "e5bcf7b6291d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("organization_brandings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("short_name", sa.String(length=60), nullable=True))
        batch_op.add_column(
            sa.Column("background_color", sa.String(length=7), nullable=True)
        )
        batch_op.add_column(sa.Column("text_color", sa.String(length=7), nullable=True))
        batch_op.add_column(
            sa.Column("support_email", sa.String(length=254), nullable=True)
        )
        batch_op.add_column(
            sa.Column("support_phone", sa.String(length=40), nullable=True)
        )
        batch_op.add_column(
            sa.Column("website_url", sa.String(length=500), nullable=True)
        )
        batch_op.add_column(
            sa.Column("footer_text", sa.String(length=300), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("organization_brandings", schema=None) as batch_op:
        batch_op.drop_column("footer_text")
        batch_op.drop_column("website_url")
        batch_op.drop_column("support_phone")
        batch_op.drop_column("support_email")
        batch_op.drop_column("text_color")
        batch_op.drop_column("background_color")
        batch_op.drop_column("short_name")

"""add demo building finance

Revision ID: d6e7f8a9b0c1
Revises: b1c2d3e4f5a6
Create Date: 2026-07-30 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "building_expenses",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("building_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("expense_month", sa.Date(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("payment_method", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_building_expenses_positive_amount"),
        sa.ForeignKeyConstraint(
            ["organization_id", "building_id"],
            ["buildings.organization_id", "buildings.id"],
            name="fk_building_expenses_org_building",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_building_expenses")),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_building_expenses_org_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "building_id",
            "source_key",
            name="uq_building_expenses_source",
        ),
    )
    op.create_index(
        "ix_building_expenses_org_building_month",
        "building_expenses",
        ["organization_id", "building_id", "expense_month"],
    )
    op.create_table(
        "apartment_expense_contributions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("expense_id", sa.Uuid(), nullable=False),
        sa.Column("apartment_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "amount >= 0", name="ck_expense_contributions_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "apartment_id"],
            ["apartments.organization_id", "apartments.id"],
            name="fk_expense_contributions_org_apartment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "expense_id"],
            ["building_expenses.organization_id", "building_expenses.id"],
            name="fk_expense_contributions_org_expense",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_apartment_expense_contributions")
        ),
        sa.UniqueConstraint(
            "expense_id",
            "apartment_id",
            name="uq_expense_contributions_expense_apartment",
        ),
    )
    op.create_index(
        "ix_expense_contributions_org_apartment",
        "apartment_expense_contributions",
        ["organization_id", "apartment_id"],
    )
    op.create_table(
        "building_bank_transactions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("building_id", sa.Uuid(), nullable=False),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("transaction_type", sa.String(30), nullable=False),
        sa.Column("inflow", sa.Numeric(14, 2), nullable=False),
        sa.Column("outflow", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("reference", sa.String(160), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("inflow >= 0", name="ck_bank_transactions_inflow"),
        sa.CheckConstraint("outflow >= 0", name="ck_bank_transactions_outflow"),
        sa.CheckConstraint(
            "NOT (inflow > 0 AND outflow > 0)",
            name="ck_bank_transactions_single_direction",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "building_id"],
            ["buildings.organization_id", "buildings.id"],
            name="fk_bank_transactions_org_building",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_building_bank_transactions")),
        sa.UniqueConstraint(
            "organization_id",
            "building_id",
            "source_key",
            name="uq_bank_transactions_source",
        ),
    )
    op.create_index(
        "ix_bank_transactions_org_building_date",
        "building_bank_transactions",
        ["organization_id", "building_id", "transaction_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bank_transactions_org_building_date",
        table_name="building_bank_transactions",
    )
    op.drop_table("building_bank_transactions")
    op.drop_index(
        "ix_expense_contributions_org_apartment",
        table_name="apartment_expense_contributions",
    )
    op.drop_table("apartment_expense_contributions")
    op.drop_index(
        "ix_building_expenses_org_building_month",
        table_name="building_expenses",
    )
    op.drop_table("building_expenses")

"""Add setup and resolution indexes

Revision ID: e3c1b7f4d921
Revises: d1a7b4e8c2f0
Create Date: 2026-05-19 00:00:02.000000

"""
from alembic import op


revision = "e3c1b7f4d921"
down_revision = "d1a7b4e8c2f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_budgets_active_scope",
        "budgets",
        ["is_active", "transaction_type", "category_id", "account_id", "owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_spend_policies_active_scope",
        "spend_policies",
        ["is_active", "transaction_type", "category_id", "account_id", "payment_method_id"],
        unique=False,
    )
    op.create_index(
        "ix_accounting_mappings_active_scope",
        "accounting_mappings",
        ["is_active", "transaction_type", "category_id", "account_id", "payment_method_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_accounting_mappings_active_scope", table_name="accounting_mappings")
    op.drop_index("ix_spend_policies_active_scope", table_name="spend_policies")
    op.drop_index("ix_budgets_active_scope", table_name="budgets")

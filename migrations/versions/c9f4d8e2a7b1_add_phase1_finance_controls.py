"""Add phase 1 finance controls

Revision ID: c9f4d8e2a7b1
Revises: b8e1f0a4c2d1
Create Date: 2026-04-21 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c9f4d8e2a7b1"
down_revision = "b8e1f0a4c2d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("alert_percent", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_budgets_account_id", "budgets", ["account_id"], unique=False)
    op.create_index("ix_budgets_category_id", "budgets", ["category_id"], unique=False)
    op.create_index("ix_budgets_owner_id", "budgets", ["owner_id"], unique=False)
    op.create_index("ix_budgets_transaction_type", "budgets", ["transaction_type"], unique=False)

    op.create_table(
        "spend_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("payment_method_id", sa.Integer(), nullable=True),
        sa.Column("max_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("require_attachment", sa.Boolean(), nullable=False),
        sa.Column("require_note", sa.Boolean(), nullable=False),
        sa.Column("block_on_over_budget", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["payment_method_id"], ["payment_methods.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_spend_policies_account_id", "spend_policies", ["account_id"], unique=False)
    op.create_index("ix_spend_policies_category_id", "spend_policies", ["category_id"], unique=False)
    op.create_index("ix_spend_policies_payment_method_id", "spend_policies", ["payment_method_id"], unique=False)
    op.create_index("ix_spend_policies_transaction_type", "spend_policies", ["transaction_type"], unique=False)

    op.create_table(
        "accounting_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("payment_method_id", sa.Integer(), nullable=True),
        sa.Column("gl_code", sa.String(length=50), nullable=False),
        sa.Column("cost_center", sa.String(length=50), nullable=True),
        sa.Column("project_code", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["payment_method_id"], ["payment_methods.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_accounting_mappings_account_id", "accounting_mappings", ["account_id"], unique=False)
    op.create_index("ix_accounting_mappings_category_id", "accounting_mappings", ["category_id"], unique=False)
    op.create_index("ix_accounting_mappings_payment_method_id", "accounting_mappings", ["payment_method_id"], unique=False)
    op.create_index("ix_accounting_mappings_transaction_type", "accounting_mappings", ["transaction_type"], unique=False)

    op.create_table(
        "transaction_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transaction_comments_transaction_id", "transaction_comments", ["transaction_id"], unique=False)
    op.create_index("ix_transaction_comments_user_id", "transaction_comments", ["user_id"], unique=False)

    op.create_table(
        "transaction_status_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("from_status", sa.String(length=40), nullable=True),
        sa.Column("to_status", sa.String(length=40), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transaction_status_history_action", "transaction_status_history", ["action"], unique=False)
    op.create_index("ix_transaction_status_history_changed_by_id", "transaction_status_history", ["changed_by_id"], unique=False)
    op.create_index("ix_transaction_status_history_transaction_id", "transaction_status_history", ["transaction_id"], unique=False)

    with op.batch_alter_table("attachments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sha256_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("duplicate_of_attachment_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_attachments_sha256_hash", ["sha256_hash"], unique=False)
        batch_op.create_foreign_key("fk_attachments_duplicate_of_attachment_id", "attachments", ["duplicate_of_attachment_id"], ["id"])

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("spend_policy_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("budget_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("accounting_mapping_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("accounting_gl_code", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("accounting_cost_center", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("accounting_project_code", sa.String(length=50), nullable=True))
        batch_op.create_index("ix_transactions_spend_policy_id", ["spend_policy_id"], unique=False)
        batch_op.create_index("ix_transactions_budget_id", ["budget_id"], unique=False)
        batch_op.create_index("ix_transactions_accounting_mapping_id", ["accounting_mapping_id"], unique=False)
        batch_op.create_foreign_key("fk_transactions_spend_policy_id", "spend_policies", ["spend_policy_id"], ["id"])
        batch_op.create_foreign_key("fk_transactions_budget_id", "budgets", ["budget_id"], ["id"])
        batch_op.create_foreign_key("fk_transactions_accounting_mapping_id", "accounting_mappings", ["accounting_mapping_id"], ["id"])


def downgrade():
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_transactions_accounting_mapping_id", type_="foreignkey")
        batch_op.drop_constraint("fk_transactions_budget_id", type_="foreignkey")
        batch_op.drop_constraint("fk_transactions_spend_policy_id", type_="foreignkey")
        batch_op.drop_index("ix_transactions_accounting_mapping_id")
        batch_op.drop_index("ix_transactions_budget_id")
        batch_op.drop_index("ix_transactions_spend_policy_id")
        batch_op.drop_column("accounting_project_code")
        batch_op.drop_column("accounting_cost_center")
        batch_op.drop_column("accounting_gl_code")
        batch_op.drop_column("accounting_mapping_id")
        batch_op.drop_column("budget_id")
        batch_op.drop_column("spend_policy_id")

    with op.batch_alter_table("attachments", schema=None) as batch_op:
        batch_op.drop_constraint("fk_attachments_duplicate_of_attachment_id", type_="foreignkey")
        batch_op.drop_index("ix_attachments_sha256_hash")
        batch_op.drop_column("duplicate_of_attachment_id")
        batch_op.drop_column("sha256_hash")

    op.drop_index("ix_transaction_status_history_transaction_id", table_name="transaction_status_history")
    op.drop_index("ix_transaction_status_history_changed_by_id", table_name="transaction_status_history")
    op.drop_index("ix_transaction_status_history_action", table_name="transaction_status_history")
    op.drop_table("transaction_status_history")

    op.drop_index("ix_transaction_comments_user_id", table_name="transaction_comments")
    op.drop_index("ix_transaction_comments_transaction_id", table_name="transaction_comments")
    op.drop_table("transaction_comments")

    op.drop_index("ix_accounting_mappings_transaction_type", table_name="accounting_mappings")
    op.drop_index("ix_accounting_mappings_payment_method_id", table_name="accounting_mappings")
    op.drop_index("ix_accounting_mappings_category_id", table_name="accounting_mappings")
    op.drop_index("ix_accounting_mappings_account_id", table_name="accounting_mappings")
    op.drop_table("accounting_mappings")

    op.drop_index("ix_spend_policies_transaction_type", table_name="spend_policies")
    op.drop_index("ix_spend_policies_payment_method_id", table_name="spend_policies")
    op.drop_index("ix_spend_policies_category_id", table_name="spend_policies")
    op.drop_index("ix_spend_policies_account_id", table_name="spend_policies")
    op.drop_table("spend_policies")

    op.drop_index("ix_budgets_transaction_type", table_name="budgets")
    op.drop_index("ix_budgets_owner_id", table_name="budgets")
    op.drop_index("ix_budgets_category_id", table_name="budgets")
    op.drop_index("ix_budgets_account_id", table_name="budgets")
    op.drop_table("budgets")

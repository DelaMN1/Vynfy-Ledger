"""Add explicit expense creation permission

Revision ID: f6a4d0be91c2
Revises: e3c1b7f4d921
Create Date: 2026-05-19 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f6a4d0be91c2"
down_revision = "e3c1b7f4d921"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("can_create_expense", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE users SET can_create_expense = true WHERE role = 'admin'")
    op.alter_column("users", "can_create_expense", server_default=None)


def downgrade():
    op.drop_column("users", "can_create_expense")

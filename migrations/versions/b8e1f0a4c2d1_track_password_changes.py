"""Track password changes

Revision ID: b8e1f0a4c2d1
Revises: 6f4b2d9f4f3c
Create Date: 2026-04-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "b8e1f0a4c2d1"
down_revision = "6f4b2d9f4f3c"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE users
        SET password_changed_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
        WHERE password_changed_at IS NULL
        """
    )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("password_changed_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("password_changed_at")

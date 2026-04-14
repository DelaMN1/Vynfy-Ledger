"""Harden auth sessions

Revision ID: 6f4b2d9f4f3c
Revises: fa0dc660b625
Create Date: 2026-04-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6f4b2d9f4f3c"
down_revision = "fa0dc660b625"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("second_factor_verified_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE user_sessions SET second_factor_verified_at = issued_at WHERE second_factor_verified_at IS NULL")

    with op.batch_alter_table("user_sessions", schema=None) as batch_op:
        batch_op.alter_column("second_factor_verified_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.create_index(batch_op.f("ix_user_sessions_second_factor_verified_at"), ["second_factor_verified_at"], unique=False)


def downgrade():
    with op.batch_alter_table("user_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_sessions_second_factor_verified_at"))
        batch_op.drop_column("second_factor_verified_at")

"""add latency indexes

Revision ID: 8c3d2fe11b6a
Revises: f6a4d0be91c2
Create Date: 2026-05-22 12:45:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "8c3d2fe11b6a"
down_revision = "f6a4d0be91c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_transactions_deleted_at", "transactions", ["deleted_at"], unique=False)
    op.create_index("ix_transactions_approved_by_id", "transactions", ["approved_by_id"], unique=False)
    op.create_index("ix_user_sessions_revoked_at", "user_sessions", ["revoked_at"], unique=False)
    op.create_index("ix_audit_logs_entity_type_entity_id", "audit_logs", ["entity_type", "entity_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_logs_entity_type_entity_id", table_name="audit_logs")
    op.drop_index("ix_user_sessions_revoked_at", table_name="user_sessions")
    op.drop_index("ix_transactions_approved_by_id", table_name="transactions")
    op.drop_index("ix_transactions_deleted_at", table_name="transactions")

from alembic import op
import sqlalchemy as sa

revision = 'fa0dc660b625'
down_revision = 'a1a14dc26ff6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('login_challenges',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('login_challenges', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_login_challenges_code_hash'), ['code_hash'], unique=False)
        batch_op.create_index(batch_op.f('ix_login_challenges_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_login_challenges_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('login_challenges', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_login_challenges_user_id'))
        batch_op.drop_index(batch_op.f('ix_login_challenges_expires_at'))
        batch_op.drop_index(batch_op.f('ix_login_challenges_code_hash'))

    op.drop_table('login_challenges')

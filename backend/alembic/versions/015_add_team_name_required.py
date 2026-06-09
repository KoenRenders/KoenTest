"""add team_name_required to activities

Revision ID: 015
Revises: 014
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('activities') as batch_op:
        batch_op.add_column(sa.Column('team_name_required', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    with op.batch_alter_table('activities') as batch_op:
        batch_op.drop_column('team_name_required')

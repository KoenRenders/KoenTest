"""Remove password_hash column from users

Revision ID: 013
Revises: 012
Create Date: 2026-06-09
"""
from alembic import op
from sqlalchemy import inspect

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("users")]
    if "password_hash" in columns:
        op.drop_column("users", "password_hash")


def downgrade():
    op.add_column("users", __import__("sqlalchemy").Column("password_hash", __import__("sqlalchemy").String(255), nullable=True))

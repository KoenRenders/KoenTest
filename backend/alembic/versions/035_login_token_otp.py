"""6-cijferige OTP-code op login-tokens

Revision ID: 035
Revises: 034
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    if "login_tokens" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("login_tokens")}
    if "otp_code" not in cols:
        op.add_column("login_tokens", sa.Column("otp_code", sa.String(6), nullable=True))


def downgrade():
    op.drop_column("login_tokens", "otp_code")

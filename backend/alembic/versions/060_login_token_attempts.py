"""login_tokens.attempts — pogingteller voor OTP-lockout (#268)

Voegt een ``attempts``-kolom toe zodat ``verify-otp`` na te veel foute codes het
token kan invalideren (brute-force-rem die niet enkel op de per-IP-limiet steunt).

Revision ID: 060
Revises: 059
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade():
    if not _has_column("login_tokens", "attempts"):
        op.add_column(
            "login_tokens",
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade():
    if _has_column("login_tokens", "attempts"):
        op.drop_column("login_tokens", "attempts")

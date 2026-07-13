"""OTP-codes gehasht opslaan (#395): kolom verbreden + bestaande plaintext wissen

Revision ID: 069
Revises: 068
"""
from alembic import op
import sqlalchemy as sa

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: alleen verbreden als de kolom nog smal is.
    op.alter_column(
        "login_tokens", "otp_code",
        type_=sa.String(64), existing_type=sa.String(6), existing_nullable=True,
    )
    # Bestaande rijen bevatten plaintext-codes; die verifiëren toch niet meer
    # tegen de hash — wissen (tokens leven max. 10 minuten, geen functieverlies).
    op.execute("UPDATE login_tokens SET otp_code = NULL WHERE otp_code IS NOT NULL AND length(otp_code) < 64")


def downgrade() -> None:
    op.execute("UPDATE login_tokens SET otp_code = NULL")
    op.alter_column(
        "login_tokens", "otp_code",
        type_=sa.String(6), existing_type=sa.String(64), existing_nullable=True,
    )

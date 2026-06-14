"""Verwijder registrations.is_waitlist — wachtlijst-functie geschrapt (#126)

De wachtlijst werd niet gebruikt; de bijbehorende code/UI/endpoints zijn weg.
Deze migratie dropt de ongebruikte kolom. Idempotent: controleert of de kolom
bestaat voor hij hem verwijdert.

Revision ID: 046
Revises: 045
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def _has_column(conn, table, column) -> bool:
    return conn.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c)"
    ), {"t": table, "c": column}).scalar()


def upgrade():
    conn = op.get_bind()
    if _has_column(conn, "registrations", "is_waitlist"):
        op.drop_column("registrations", "is_waitlist")


def downgrade():
    conn = op.get_bind()
    if not _has_column(conn, "registrations", "is_waitlist"):
        op.add_column(
            "registrations",
            sa.Column("is_waitlist", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        # server_default enkel voor de bestaande rijen; daarna weghalen zodat het
        # gedrag overeenkomt met het oude model (default in de app-laag).
        op.alter_column("registrations", "is_waitlist", server_default=None)

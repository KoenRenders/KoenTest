"""Audit van de contactgegevens van een inschrijving (#624).

Een beheerder mag een tikfout in naam, e-mail of gsm rechtzetten. Zonder spoor is
zo'n stille correctie op iemands contactgegevens niet te verklaren, dus krijgt ze —
net als elke andere mutatie — een append-only history-rij. Idempotent: de tabel
wordt enkel aangemaakt als ze nog niet bestaat.

Revision ID: 090
Revises: 089
"""
import sqlalchemy as sa
from alembic import op

revision = "090"
down_revision = "089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bestaat = bind.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'activities' AND table_name = 'registration_history'"
    )).first()
    if bestaat:
        return

    op.create_table(
        "registration_history",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
        sa.Column("registration_id", sa.Integer(), nullable=False, index=True),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False, index=True),
        schema="activities",
    )


def downgrade() -> None:
    op.drop_table("registration_history", schema="activities")

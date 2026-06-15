"""business_events-tabel — first-party business-events (#152, laag 2)

GDPR-conforme, server-side gelogde gebeurtenissen op de kernflows (registratie,
betaling, hernieuwing). Bewust GEEN ForeignKeys (het event overleeft het
verwijderen van de bron-rij — zie app/models/business_event.py).

Idempotent: controleert of de tabel/indexen al bestaan voor het aanmaken.

Revision ID: 048
Revises: 047
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import text

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None

TABLE = "business_events"


def _has_table(conn, table) -> bool:
    return conn.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t)"
    ), {"t": table}).scalar()


def _has_index(conn, name) -> bool:
    return conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"
    ), {"n": name}).scalar()


def upgrade():
    conn = op.get_bind()
    if not _has_table(conn, TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(length=50), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("member_id", sa.Integer(), nullable=True),
            sa.Column("activity_id", sa.Integer(), nullable=True),
            sa.Column("payment_record_id", sa.String(length=36), nullable=True),
            sa.Column("payload", JSONB(), nullable=True),
            sa.Column("session_ref", sa.String(length=64), nullable=True),
        )
    for col in ("id", "event_type", "occurred_at", "member_id",
                "activity_id", "payment_record_id", "session_ref"):
        idx = f"ix_{TABLE}_{col}"
        if not _has_index(conn, idx):
            op.create_index(idx, TABLE, [col])


def downgrade():
    conn = op.get_bind()
    if _has_table(conn, TABLE):
        op.drop_table(TABLE)

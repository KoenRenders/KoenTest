"""Fase 3 (#401): betalingstabellen naar Postgres-schema 'payment'

Zelfde recept als 071/075/076/078 (§13): puur namespacing via
ALTER TABLE ... SET SCHEMA; FK's binnen het component verhuizen mee, en er
zijn geen FK's van of naar andere schema's (payable is al een soft-ref).

Revision ID: 079
Revises: 078
"""
from alembic import op
import sqlalchemy as sa

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None

TABLES = ["gateway_payments", "payment_records", "payment_record_history"]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS payment")
    bind = op.get_bind()
    for table in TABLES:
        in_public = bind.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"), {"t": table}).scalar()
        if in_public:
            op.execute(f"ALTER TABLE public.{table} SET SCHEMA payment")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"ALTER TABLE payment.{table} SET SCHEMA public")

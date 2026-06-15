"""Soft delete — activiteiten, betalingen, gebruikers: deleted_at + partiële uniciteit (#166)

Stage 2/3 van de soft-delete-uitrol: ``deleted_at`` op de activiteiten-,
betaal- en gebruikerstabellen, en de resterende unieke constraints omgezet naar
partiële unieke indexen (``WHERE deleted_at IS NULL``).

Revision ID: 051
Revises: 050
"""
from alembic import op
import sqlalchemy as sa

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None

_TABLES = [
    "activities", "activity_dates", "activity_sub_registrations", "activity_products",
    "registrations", "registration_items",
    "payment_records", "gateway_payments", "users",
]


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in _TABLES:
        cols = [c["name"] for c in insp.get_columns(table)]
        if "deleted_at" not in cols:
            op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
            op.create_index(f"ix_{table}_deleted_at", table, ["deleted_at"])

    # users.email: volledige uniciteit (constraint én unieke index) → partieel.
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key")
    op.execute("DROP INDEX IF EXISTS ix_users_email")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email "
               "ON users (email) WHERE deleted_at IS NULL")

    # payment_records.gateway_payment_id: unieke index → partieel.
    op.execute("DROP INDEX IF EXISTS uq_payment_records_gateway_payment_id")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_records_gateway_payment_id "
               "ON payment_records (gateway_payment_id) WHERE gateway_payment_id IS NOT NULL AND deleted_at IS NULL")


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_users_email")
    op.execute("ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email)")
    op.execute("DROP INDEX IF EXISTS uq_payment_records_gateway_payment_id")
    op.execute("CREATE UNIQUE INDEX uq_payment_records_gateway_payment_id "
               "ON payment_records (gateway_payment_id) WHERE gateway_payment_id IS NOT NULL")

    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in _TABLES:
        cols = [c["name"] for c in insp.get_columns(table)]
        if "deleted_at" in cols:
            op.drop_index(f"ix_{table}_deleted_at", table_name=table)
            op.drop_column(table, "deleted_at")

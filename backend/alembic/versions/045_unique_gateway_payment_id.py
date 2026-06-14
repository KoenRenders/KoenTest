"""Unieke index op payment_records.gateway_payment_id (#91)

Eén gateway-betaling (Mollie) mag maar één PaymentRecord backen. Een partiële
unieke index (WHERE gateway_payment_id IS NOT NULL) dwingt dat af op DB-niveau,
zodat een herhaalde/gelijktijdige webhook of een per ongeluk dubbele koppeling
nooit meerdere records kan muteren. Handmatige records (cash/overschrijving)
hebben geen gateway_payment_id en blijven dus toegestaan (NULL valt buiten de index).

Idempotent: controleert of de index al bestaat voor hij hem aanmaakt.

Revision ID: 045
Revises: 044
Create Date: 2026-06-14
"""
from alembic import op
from sqlalchemy import text

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_payment_records_gateway_payment_id"


def upgrade():
    conn = op.get_bind()
    exists = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"
    ), {"n": INDEX_NAME}).scalar()
    if not exists:
        op.create_index(
            INDEX_NAME,
            "payment_records",
            ["gateway_payment_id"],
            unique=True,
            postgresql_where=text("gateway_payment_id IS NOT NULL"),
        )


def downgrade():
    conn = op.get_bind()
    exists = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"
    ), {"n": INDEX_NAME}).scalar()
    if exists:
        op.drop_index(INDEX_NAME, table_name="payment_records")

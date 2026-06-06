"""Add payment domain tables

Revision ID: 011
Revises: 004
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "011"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = inspector.get_table_names()

    if "gateway_payments" not in existing:
        op.create_table(
            "gateway_payments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("provider", sa.String(20), nullable=False),
            sa.Column("provider_payment_id", sa.String(100), nullable=True),
            sa.Column("amount", sa.Numeric(10, 2), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("checkout_url", sa.String(500), nullable=True),
            sa.Column("description", sa.String(200), nullable=True),
            sa.Column("payment_metadata", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("updated_at", sa.DateTime, nullable=False),
        )
        op.create_index("ix_gateway_payments_provider_payment_id", "gateway_payments", ["provider_payment_id"])

    if "payment_records" not in existing:
        op.create_table(
            "payment_records",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("payable_type", sa.String(50), nullable=False),
            sa.Column("payable_id", sa.Integer, nullable=False),
            sa.Column("amount", sa.Numeric(10, 2), nullable=False),
            sa.Column("method", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("gateway_payment_id", sa.String(36), sa.ForeignKey("gateway_payments.id"), nullable=True),
            sa.Column("note", sa.String(200), nullable=True),
            sa.Column("paid_at", sa.DateTime, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("updated_at", sa.DateTime, nullable=False),
        )
        op.create_index("ix_payment_records_payable", "payment_records", ["payable_type", "payable_id"])


def downgrade():
    op.drop_table("payment_records")
    op.drop_table("gateway_payments")

"""Remove webshop tables (products, orders, order_items)

Revision ID: 006
Revises: 005
Create Date: 2026-06-05
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("webshop_products")


def downgrade():
    pass

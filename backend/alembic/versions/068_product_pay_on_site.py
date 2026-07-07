"""activiteiten: product-optie 'ter plaatse betalen (eigen budget)' (#373)

``activity_products`` krijgt ``pay_on_site`` (bool, default false): het product
moet ingeschreven worden maar wordt niet via het portaal afgerekend (net als
``is_free`` telt het niet mee in het Mollie-totaal). Idempotent.

Revision ID: 068
Revises: 067
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade():
    if not _has_column("activity_products", "pay_on_site"):
        op.add_column(
            "activity_products",
            sa.Column("pay_on_site", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade():
    if _has_column("activity_products", "pay_on_site"):
        op.drop_column("activity_products", "pay_on_site")

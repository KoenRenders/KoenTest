"""an order carries the secret of its thank-you link

Koen, 16 October 2026: the thank-you page no longer opens on an order id alone.
Each order gets a secret key, made when it is placed, and the thank-you link
carries it; the page opens only for the order whose key it is. A wrong, missing
or old-form link answers 404, so ids reveal nothing. An order placed before this
migration has no key and no thank-you page by link (the buyer has the mail).
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
revision = "312_2026_10_16_162902"
down_revision = "311_2026_10_16_123616"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sales.sales_orders ADD COLUMN IF NOT EXISTS secret_key VARCHAR(64)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_orders_secret_key "
        "ON sales.sales_orders (secret_key)"
    )


def downgrade() -> None:
    # Schema and data: the keys go with their column. An order loses nothing it
    # needs; its thank-you page is then not reachable by link any more.
    op.execute("DROP INDEX IF EXISTS sales.uq_sales_orders_secret_key")
    op.execute("ALTER TABLE sales.sales_orders DROP COLUMN IF EXISTS secret_key")

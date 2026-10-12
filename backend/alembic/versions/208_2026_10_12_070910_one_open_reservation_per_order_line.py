"""one open reservation per order line

CR-21, phase 2. One order line holds one open reservation: a partial unique
index on the OPEN ones, so a line reserved twice is refused at rest — the same
rule `stock.reserve` now refuses in the service. A delivered or cancelled
reservation does not block a new one; only an OPEN one does.
"""

from alembic import op

# The id is a timestamp, not a sequence number (#951). The number at the front
# of the FILE NAME is for readability only — alembic ignores it; the head is
# what `alembic heads` says.
revision = "208_2026_10_12_070910"
down_revision = "207_2026_10_10_101936"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_reservations_open_line "
        "ON stock.stock_reservations (tenant_id, order_line_id) "
        "WHERE status = 'OPEN'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS stock.uq_stock_reservations_open_line")

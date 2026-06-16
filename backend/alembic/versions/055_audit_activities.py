"""audit-tabellen voor activiteiten/datums/onderdelen/producten (#189)

Append-only history-tabellen met dezelfde audit-metadata (HistoryMixin) als de
bestaande history-tabellen, zodat ook wijzigingen en soft-deletes van het
activiteiten-domein traceerbaar zijn. Geen FK naar de bron, geen cascade.

Revision ID: 055
Revises: 054
"""
from alembic import op
import sqlalchemy as sa

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def _meta_cols():
    """Verse audit-metadata-kolommen (HistoryMixin) per tabel."""
    return [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def _create(insp, table, *cols, key_col):
    if table in insp.get_table_names():
        return
    op.create_table(
        table,
        *_meta_cols(),
        *cols,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(f"ix_{table}_recorded_at", table, ["recorded_at"])
    op.create_index(f"ix_{table}_{key_col}", table, [key_col])


def upgrade():
    insp = sa.inspect(op.get_bind())
    _create(
        insp, "activity_history",
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        key_col="activity_id",
    )
    _create(
        insp, "activity_date_history",
        sa.Column("activity_date_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        key_col="activity_date_id",
    )
    _create(
        insp, "component_history",
        sa.Column("component_id", sa.Integer(), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("member_price", sa.Numeric(10, 2), nullable=True),
        key_col="component_id",
    )
    _create(
        insp, "product_history",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("member_price", sa.Numeric(10, 2), nullable=True),
        key_col="product_id",
    )


def downgrade():
    insp = sa.inspect(op.get_bind())
    for table in ("product_history", "component_history",
                  "activity_date_history", "activity_history"):
        if table in insp.get_table_names():
            op.drop_table(table)

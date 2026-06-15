"""payment_records.structured_communication + OGM-sequence (#157)

Voegt een kolom toe voor de gestructureerde mededeling (OGM) op een betaling, en
een Postgres-sequence die de unieke, oplopende basisnummers levert.

Revision ID: 047
Revises: 046
"""
from alembic import op
import sqlalchemy as sa

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns("payment_records")]
    if "structured_communication" not in cols:
        op.add_column(
            "payment_records",
            sa.Column("structured_communication", sa.String(length=20), nullable=True),
        )
    # Unieke, oplopende bron voor de gestructureerde mededeling.
    op.execute("CREATE SEQUENCE IF NOT EXISTS payment_ogm_seq START 1")


def downgrade():
    op.execute("DROP SEQUENCE IF EXISTS payment_ogm_seq")
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns("payment_records")]
    if "structured_communication" in cols:
        op.drop_column("payment_records", "structured_communication")

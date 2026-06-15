"""registration_item_history — audit van bestelregels (#84)

Append-only history-tabel die elke insert/update/delete van een RegistrationItem
vastlegt, met dezelfde audit-metadata (HistoryMixin) als de andere history-tabellen
(zie 026). Geen FK naar de bron en geen cascade: de history overleeft het
verwijderen van de bestelregel.

Revision ID: 049
Revises: 048
"""
from alembic import op
import sqlalchemy as sa

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "registration_item_history" in insp.get_table_names():
        return
    op.create_table(
        "registration_item_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("registration_item_id", sa.Integer(), nullable=False),
        sa.Column("registration_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_registration_item_history_recorded_at",
                    "registration_item_history", ["recorded_at"])
    op.create_index("ix_registration_item_history_registration_item_id",
                    "registration_item_history", ["registration_item_id"])
    op.create_index("ix_registration_item_history_registration_id",
                    "registration_item_history", ["registration_id"])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "registration_item_history" in insp.get_table_names():
        op.drop_table("registration_item_history")

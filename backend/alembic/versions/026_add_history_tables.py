"""Voeg history-tabellen toe (append-only) voor betalingen en masterdata

Revision ID: 026
Revises: 025
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


# Gedeelde audit-metadatakolommen voor elke history-tabel.
def _audit_columns():
    return [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    ]


# (tabelnaam, [extra snapshot-kolommen], [(index_kolom)])
HISTORY_TABLES = {
    "person_history": (
        [
            sa.Column("person_id", sa.Integer(), nullable=False),
            sa.Column("last_name", sa.String(100), nullable=True),
            sa.Column("first_name", sa.String(100), nullable=True),
            sa.Column("date_of_birth", sa.Date(), nullable=True),
            sa.Column("gender_code", sa.String(10), nullable=True),
        ],
        ["person_id"],
    ),
    "member_history": (
        [
            sa.Column("member_id", sa.Integer(), nullable=False),
            sa.Column("board_member_id", sa.Integer(), nullable=True),
        ],
        ["member_id"],
    ),
    "member_person_history": (
        [
            sa.Column("member_person_id", sa.Integer(), nullable=False),
            sa.Column("member_id", sa.Integer(), nullable=True),
            sa.Column("person_id", sa.Integer(), nullable=True),
            sa.Column("relation_type", sa.String(10), nullable=True),
        ],
        ["member_person_id", "member_id", "person_id"],
    ),
    "membership_history": (
        [
            sa.Column("membership_id", sa.Integer(), nullable=False),
            sa.Column("member_id", sa.Integer(), nullable=True),
            sa.Column("year", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("valid_from", sa.Date(), nullable=True),
            sa.Column("valid_to", sa.Date(), nullable=True),
        ],
        ["membership_id", "member_id"],
    ),
    "address_history": (
        [
            sa.Column("address_id", sa.Integer(), nullable=False),
            sa.Column("person_id", sa.Integer(), nullable=True),
            sa.Column("street", sa.String(255), nullable=True),
            sa.Column("house_number", sa.String(20), nullable=True),
            sa.Column("bus_number", sa.String(10), nullable=True),
            sa.Column("postal_code_id", sa.Integer(), nullable=True),
        ],
        ["address_id", "person_id"],
    ),
    "contact_detail_history": (
        [
            sa.Column("contact_detail_id", sa.Integer(), nullable=False),
            sa.Column("person_id", sa.Integer(), nullable=True),
            sa.Column("contact_type_code", sa.String(10), nullable=True),
            sa.Column("value", sa.String(255), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=True),
        ],
        ["contact_detail_id", "person_id"],
    ),
    "payment_record_history": (
        [
            sa.Column("payment_record_id", sa.String(36), nullable=False),
            sa.Column("payable_type", sa.String(50), nullable=True),
            sa.Column("payable_id", sa.Integer(), nullable=True),
            sa.Column("amount", sa.Numeric(10, 2), nullable=True),
            sa.Column("amount_paid", sa.Numeric(10, 2), nullable=True),
            sa.Column("method", sa.String(20), nullable=True),
            sa.Column("status", sa.String(20), nullable=True),
            sa.Column("gateway_payment_id", sa.String(36), nullable=True),
            sa.Column("note", sa.String(200), nullable=True),
            sa.Column("paid_at", sa.DateTime(), nullable=True),
        ],
        ["payment_record_id"],
    ),
}


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    existing = set(insp.get_table_names())

    for table_name, (extra_cols, index_cols) in HISTORY_TABLES.items():
        if table_name in existing:
            continue
        op.create_table(
            table_name,
            *_audit_columns(),
            *extra_cols,
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(f"ix_{table_name}_recorded_at", table_name, ["recorded_at"])
        for col in index_cols:
            op.create_index(f"ix_{table_name}_{col}", table_name, [col])


def downgrade():
    for table_name, (_extra, index_cols) in HISTORY_TABLES.items():
        for col in index_cols:
            op.drop_index(f"ix_{table_name}_{col}", table_name)
        op.drop_index(f"ix_{table_name}_recorded_at", table_name)
        op.drop_table(table_name)

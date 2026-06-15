"""payment_records: refund-grootboek — type (charge/refund) + refund_of_id (#83)

Een terugbetaling is een apart PaymentRecord met een negatief bedrag, een
expliciet ``type`` (charge/refund) en een self-FK ``refund_of_id`` naar de charge
die het terugdraait. Beide kolommen worden gespiegeld op payment_record_history
zodat de audit-tijdlijn volledig blijft.

Revision ID: 048
Revises: 047
"""
from alembic import op
import sqlalchemy as sa

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    pr_cols = [c["name"] for c in insp.get_columns("payment_records")]
    if "type" not in pr_cols:
        op.add_column(
            "payment_records",
            sa.Column("type", sa.String(length=10), nullable=False, server_default="charge"),
        )
    if "refund_of_id" not in pr_cols:
        op.add_column(
            "payment_records",
            sa.Column("refund_of_id", sa.String(length=36), nullable=True),
        )

    fks = [fk["name"] for fk in insp.get_foreign_keys("payment_records")]
    if "fk_payment_records_refund_of" not in fks:
        op.create_foreign_key(
            "fk_payment_records_refund_of",
            "payment_records", "payment_records",
            ["refund_of_id"], ["id"],
            ondelete="SET NULL",
        )

    checks = [c["name"] for c in insp.get_check_constraints("payment_records")]
    if "ck_payment_records_type" not in checks:
        op.create_check_constraint(
            "ck_payment_records_type", "payment_records",
            "type IN ('charge', 'refund')",
        )

    indexes = [ix["name"] for ix in insp.get_indexes("payment_records")]
    if "ix_payment_records_refund_of_id" not in indexes:
        op.create_index(
            "ix_payment_records_refund_of_id", "payment_records", ["refund_of_id"]
        )

    # History-spiegel: geen FK/constraint (history-conventie), enkel kolommen.
    h_cols = [c["name"] for c in insp.get_columns("payment_record_history")]
    if "type" not in h_cols:
        op.add_column(
            "payment_record_history",
            sa.Column("type", sa.String(length=10), nullable=True),
        )
    if "refund_of_id" not in h_cols:
        op.add_column(
            "payment_record_history",
            sa.Column("refund_of_id", sa.String(length=36), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    indexes = [ix["name"] for ix in insp.get_indexes("payment_records")]
    if "ix_payment_records_refund_of_id" in indexes:
        op.drop_index("ix_payment_records_refund_of_id", table_name="payment_records")

    checks = [c["name"] for c in insp.get_check_constraints("payment_records")]
    if "ck_payment_records_type" in checks:
        op.drop_constraint("ck_payment_records_type", "payment_records", type_="check")

    fks = [fk["name"] for fk in insp.get_foreign_keys("payment_records")]
    if "fk_payment_records_refund_of" in fks:
        op.drop_constraint("fk_payment_records_refund_of", "payment_records", type_="foreignkey")

    pr_cols = [c["name"] for c in insp.get_columns("payment_records")]
    if "refund_of_id" in pr_cols:
        op.drop_column("payment_records", "refund_of_id")
    if "type" in pr_cols:
        op.drop_column("payment_records", "type")

    h_cols = [c["name"] for c in insp.get_columns("payment_record_history")]
    if "refund_of_id" in h_cols:
        op.drop_column("payment_record_history", "refund_of_id")
    if "type" in h_cols:
        op.drop_column("payment_record_history", "type")

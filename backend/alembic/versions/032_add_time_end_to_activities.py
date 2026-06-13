"""Voeg activities.time_end toe (eindtijdstip van een activiteit)

Optioneel eindtijdstip, bv. de verwachte terugkomst bij een uitstap. Niet
ingevuld = niet tonen. Idempotent: controleert of de kolom al bestaat.

Revision ID: 032
Revises: 031
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    if "activities" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("activities")}
    if "time_end" not in cols:
        op.add_column("activities", sa.Column("time_end", sa.Time(), nullable=True))


def downgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    if "activities" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("activities")}
    if "time_end" in cols:
        op.drop_column("activities", "time_end")

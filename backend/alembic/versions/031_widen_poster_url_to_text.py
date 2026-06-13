"""Verbreed activities.poster_url van String(500) naar Text

Een flyer-hyperlink (bv. een lange Google Drive- of redirect-URL) past niet
altijd in 500 tekens; dan faalt het opslaan van de activiteit. Text heeft geen
lengtelimiet. Idempotent: controleert het huidige kolomtype vóór het wijzigen.

Revision ID: 031
Revises: 030
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    if "activities" not in set(insp.get_table_names()):
        return
    col = next(
        (c for c in insp.get_columns("activities") if c["name"] == "poster_url"),
        None,
    )
    if col is None:
        return
    # Alleen wijzigen als het nog geen Text is (idempotent).
    if not isinstance(col["type"], sa.Text):
        op.alter_column(
            "activities",
            "poster_url",
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade():
    op.alter_column(
        "activities",
        "poster_url",
        type_=sa.String(500),
        existing_nullable=True,
    )

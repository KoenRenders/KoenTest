"""Voeg external_numbers tabel toe (extern lidnummer per persoon)

Revision ID: 025
Revises: 024
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    if "external_numbers" not in insp.get_table_names():
        op.create_table(
            "external_numbers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("person_id", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(50), nullable=False, server_default="ledenadministratie"),
            sa.Column("external_id", sa.String(50), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["person_id"], ["persons.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source", "external_id", name="uq_external_numbers_source_external_id"),
        )
        op.create_index("ix_external_numbers_person_id", "external_numbers", ["person_id"])


def downgrade():
    op.drop_index("ix_external_numbers_person_id", "external_numbers")
    op.drop_table("external_numbers")

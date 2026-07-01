"""form engine: branching per keuze-optie (#336)

``form_field_options`` krijgt:
- ``skip_to_section_id``: bij selectie van deze optie springt de invuller naar die
  sectie (FK -> form_sections, SET NULL).
- ``skip_to_end``: bij selectie springt de invuller naar het einde.

Enkel zinvol voor radio/select-velden. Idempotent (bestaanschecks).

Revision ID: 064
Revises: 063
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def _insp():
    return inspect(op.get_bind())


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _insp().get_columns(table))


def upgrade():
    # Sectie-navigatie (#336): onvoorwaardelijke sprong na een sectie.
    if not _has_column("form_sections", "next_section_id"):
        op.add_column(
            "form_sections",
            sa.Column("next_section_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_form_sections_next_section", "form_sections", "form_sections",
            ["next_section_id"], ["id"], ondelete="SET NULL",
        )
    if not _has_column("form_sections", "next_is_end"):
        op.add_column(
            "form_sections",
            sa.Column("next_is_end", sa.Boolean(), nullable=False, server_default="false"),
        )

    if not _has_column("form_field_options", "skip_to_section_id"):
        op.add_column(
            "form_field_options",
            sa.Column("skip_to_section_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_form_field_options_skip_section", "form_field_options", "form_sections",
            ["skip_to_section_id"], ["id"], ondelete="SET NULL",
        )
    if not _has_column("form_field_options", "skip_to_end"):
        op.add_column(
            "form_field_options",
            sa.Column("skip_to_end", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade():
    if _has_column("form_field_options", "skip_to_end"):
        op.drop_column("form_field_options", "skip_to_end")
    if _has_column("form_field_options", "skip_to_section_id"):
        op.drop_constraint("fk_form_field_options_skip_section", "form_field_options", type_="foreignkey")
        op.drop_column("form_field_options", "skip_to_section_id")
    if _has_column("form_sections", "next_is_end"):
        op.drop_column("form_sections", "next_is_end")
    if _has_column("form_sections", "next_section_id"):
        op.drop_constraint("fk_form_sections_next_section", "form_sections", type_="foreignkey")
        op.drop_column("form_sections", "next_section_id")

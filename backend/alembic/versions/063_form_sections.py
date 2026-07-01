"""form engine: secties + info-veldtype + "Andere…"-optie (#335, #337)

- ``form_sections``: titel + beschrijving + positie per sectie.
- ``form_fields.section_id``: optionele koppeling aan een sectie (NULL = ongegroepeerd).
- ``field_type``-CHECK uitgebreid met ``info`` (louter tekstblok, geen antwoord).
- ``form_field_options.is_other``: "Andere…"-optie met vrij tekstveld (#337).

Idempotent (bestaanschecks).

Revision ID: 063
Revises: 062
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def _insp():
    return inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _insp().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _insp().get_columns(table))


def upgrade():
    if not _has_table("form_sections"):
        op.create_table(
            "form_sections",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("form_id", sa.Integer(), sa.ForeignKey("forms.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=300), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_form_sections_form_id", "form_sections", ["form_id"])

    if not _has_column("form_fields", "section_id"):
        op.add_column(
            "form_fields",
            sa.Column("section_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "fk_form_fields_section_id", "form_fields", "form_sections",
            ["section_id"], ["id"], ondelete="CASCADE",
        )
        op.create_index("ix_form_fields_section_id", "form_fields", ["section_id"])

    # CHECK op field_type uitbreiden met 'info'. Drop-if-exists + hercreatie = idempotent.
    op.execute("ALTER TABLE form_fields DROP CONSTRAINT IF EXISTS ck_form_fields_type")
    op.create_check_constraint(
        "ck_form_fields_type", "form_fields",
        "field_type IN ('text', 'textarea', 'number', 'email', 'select', 'radio', 'checkbox', 'rating', 'info')",
    )

    # "Andere…"-optie (#337).
    if not _has_column("form_field_options", "is_other"):
        op.add_column(
            "form_field_options",
            sa.Column("is_other", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade():
    if _has_column("form_field_options", "is_other"):
        op.drop_column("form_field_options", "is_other")
    op.execute("ALTER TABLE form_fields DROP CONSTRAINT IF EXISTS ck_form_fields_type")
    if _has_column("form_fields", "section_id"):
        op.drop_constraint("fk_form_fields_section_id", "form_fields", type_="foreignkey")
        op.drop_index("ix_form_fields_section_id", table_name="form_fields")
        op.drop_column("form_fields", "section_id")
    if _has_table("form_sections"):
        op.drop_table("form_sections")

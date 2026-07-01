"""form engine: anoniem-vlag + phone-veldtype (#343, #344)

- ``forms.is_anonymous``: anoniem formulier (geen contactblok/mail/submitter).
- ``field_type``-CHECK uitgebreid met ``phone``.

Idempotent (bestaanschecks).

Revision ID: 065
Revises: 064
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def _insp():
    return inspect(op.get_bind())


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _insp().get_columns(table))


def upgrade():
    if not _has_column("forms", "is_anonymous"):
        op.add_column(
            "forms",
            sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default="false"),
        )
    op.execute("ALTER TABLE form_fields DROP CONSTRAINT IF EXISTS ck_form_fields_type")
    op.create_check_constraint(
        "ck_form_fields_type", "form_fields",
        "field_type IN ('text', 'textarea', 'number', 'email', 'select', 'radio', 'checkbox', 'rating', 'info', 'phone')",
    )


def downgrade():
    op.execute("ALTER TABLE form_fields DROP CONSTRAINT IF EXISTS ck_form_fields_type")
    op.create_check_constraint(
        "ck_form_fields_type", "form_fields",
        "field_type IN ('text', 'textarea', 'number', 'email', 'select', 'radio', 'checkbox', 'rating', 'info')",
    )
    if _has_column("forms", "is_anonymous"):
        op.drop_column("forms", "is_anonymous")

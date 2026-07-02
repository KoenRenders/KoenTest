"""form engine: configureerbare rating-schaal (#341)

``form_fields`` krijgt ``rating_max`` (aantal punten) + optionele eindpunt-labels
``rating_low_label`` / ``rating_high_label``. Leeg + 5 punten → standaard
"zeer slecht → zeer goed".

Idempotent (bestaanschecks).

Revision ID: 066
Revises: 065
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def _insp():
    return inspect(op.get_bind())


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in _insp().get_columns(table))


def upgrade():
    if not _has_column("form_fields", "rating_max"):
        op.add_column("form_fields", sa.Column("rating_max", sa.Integer(), nullable=True))
    if not _has_column("form_fields", "rating_low_label"):
        op.add_column("form_fields", sa.Column("rating_low_label", sa.String(length=100), nullable=True))
    if not _has_column("form_fields", "rating_high_label"):
        op.add_column("form_fields", sa.Column("rating_high_label", sa.String(length=100), nullable=True))


def downgrade():
    for col in ("rating_high_label", "rating_low_label", "rating_max"):
        if _has_column("form_fields", col):
            op.drop_column("form_fields", col)

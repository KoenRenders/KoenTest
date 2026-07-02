"""form engine: rating-CHECK verruimen naar 1..10 (#341)

De configureerbare rating-schaal (#341) laat een maximum tot 10 toe, maar de
oorspronkelijke CHECK uit 062 (``value_rating BETWEEN 1 AND 5``) blokkeerde elke
waarde > 5 met een IntegrityError (interne serverfout bij het indienen). We
vervangen de constraint door ``value_rating BETWEEN 1 AND 10``.

Idempotent: laat de oude constraint vallen als hij bestaat en zet de nieuwe.

Revision ID: 067
Revises: 066
"""
from alembic import op
from sqlalchemy import inspect

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None

_OLD = "ck_form_answer_rating_range"


def _has_constraint(table: str, name: str) -> bool:
    insp = inspect(op.get_bind())
    return any(c["name"] == name for c in insp.get_check_constraints(table))


def upgrade():
    if _has_constraint("form_submission_answers", _OLD):
        op.drop_constraint(_OLD, "form_submission_answers", type_="check")
    op.create_check_constraint(
        _OLD, "form_submission_answers",
        "value_rating IS NULL OR (value_rating BETWEEN 1 AND 10)",
    )


def downgrade():
    if _has_constraint("form_submission_answers", _OLD):
        op.drop_constraint(_OLD, "form_submission_answers", type_="check")
    op.create_check_constraint(
        _OLD, "form_submission_answers",
        "value_rating IS NULL OR (value_rating BETWEEN 1 AND 5)",
    )

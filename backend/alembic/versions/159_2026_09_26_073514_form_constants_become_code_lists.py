"""form constants become code lists

CR-12 phase 4, the forms domain. Two lists that were module tuples: the form
status and the field type.

**The field type's `CHECK` goes, and it is the clearest case in this change
request for why.** `ck_form_fields_type` was written by migration 062 and had
to be rewritten twice since — migration 063 to add `info`, migration 065 to
add `phone`. Three migrations for two values that a list would have taken as
two rows. The foreign key says the same thing and never needs rewriting.

The 1–5 rating scale is **not** a list (§B4.10): a Likert scale is copy, not a
vocabulary, and `RATING_LABELS` stays behind `_()`.

No data change: every value both columns hold is already one of the codes.
"""
from alembic import op
import sqlalchemy as sa

from app.domains.forms.codes import FIELD_TYPE_CODES, FORM_STATUS_CODES
from app.kernel.codes import create_code_list


# The id is a timestamp, not a sequence number (#951).
revision = '159_2026_09_26_073514'
down_revision = '158_2026_09_26_071916'
branch_labels = None
depends_on = None

LISTS = (
    ("form_status", FORM_STATUS_CODES, 20, "form.forms.status"),
    ("field_type", FIELD_TYPE_CODES, 20, "form.form_fields.field_type"),
)

#: The CHECK that says what the new foreign key says — and that has already
#: cost three migrations (062, 063, 065).
CHECKS = (("form_fields", "ck_form_fields_type"),)


def upgrade() -> None:
    for name, codes, length, column in LISTS:
        create_code_list(op, schema="form", name=name, codes=codes,
                         fk_from=(column,), code_length=length)

    inspector = sa.inspect(op.get_bind())
    for table, constraint in CHECKS:
        existing = {c["name"] for c in
                    inspector.get_check_constraints(table, schema="form")}
        if constraint in existing:
            op.drop_constraint(constraint, table, schema="form", type_="check")


def downgrade() -> None:
    # Schema only: this migration wrote no form data.
    op.create_check_constraint(
        "ck_form_fields_type", "form_fields",
        "field_type IN ('text', 'textarea', 'number', 'email', 'select', "
        "'radio', 'checkbox', 'rating', 'info', 'phone')", schema="form")
    for name, _codes, _length, column in LISTS:
        _schema, table, column_name = column.split(".")
        op.drop_constraint(f"fk_{table}_{column_name}_code", table,
                           schema="form", type_="foreignkey")
        op.drop_table(f"{name}_labels", schema="form")
        op.drop_table(f"{name}_codes", schema="form")

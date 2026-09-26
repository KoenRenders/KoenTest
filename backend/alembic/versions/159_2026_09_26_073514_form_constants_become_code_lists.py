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


# De id is een tijdstempel en geen volgnummer (#951).
revision = '159_2026_09_26_073514'
down_revision = '158_2026_09_26_071916'
branch_labels = None
depends_on = None

LIJSTEN = (
    ("form_status", FORM_STATUS_CODES, 20, "form.forms.status"),
    ("field_type", FIELD_TYPE_CODES, 20, "form.form_fields.field_type"),
)

#: De CHECK die hetzelfde zegt als de nieuwe foreign key — en die al drie
#: migraties gekost heeft (062, 063, 065).
CHECKS = (("form_fields", "ck_form_fields_type"),)


def upgrade() -> None:
    for naam, codes, lengte, kolom in LIJSTEN:
        create_code_list(op, schema="form", name=naam, codes=codes,
                         fk_from=(kolom,), code_length=lengte)

    inspecteur = sa.inspect(op.get_bind())
    for tabel, constraint in CHECKS:
        bestaand = {c["name"] for c in
                    inspecteur.get_check_constraints(tabel, schema="form")}
        if constraint in bestaand:
            op.drop_constraint(constraint, tabel, schema="form", type_="check")


def downgrade() -> None:
    # Alleen schema: deze migratie schreef geen formulierdata.
    op.create_check_constraint(
        "ck_form_fields_type", "form_fields",
        "field_type IN ('text', 'textarea', 'number', 'email', 'select', "
        "'radio', 'checkbox', 'rating', 'info', 'phone')", schema="form")
    for naam, _codes, _lengte, kolom in LIJSTEN:
        _schema, tabel, kolomnaam = kolom.split(".")
        op.drop_constraint(f"fk_{tabel}_{kolomnaam}_code", tabel,
                           schema="form", type_="foreignkey")
        op.drop_table(f"{naam}_labels", schema="form")
        op.drop_table(f"{naam}_codes", schema="form")

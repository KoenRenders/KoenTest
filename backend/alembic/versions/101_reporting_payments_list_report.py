"""Reporting phase 5 (#841 point 4): the payments export as a saved report.

One of the four. It reproduces `/admin/betalingen/export` out of the universe —
same columns, same order, same totals row — and stands beside it. The existing
button, its route and its output are untouched (§2.8, and
`test_reporting_changes_nothing.py` holds it to that), and this report does not
call it: it reads the universe, the way every other report does.

**The price, stated where it is paid.** Two independent roads now lead to
comparable output and they can drift apart. That was accepted deliberately; what
keeps it honest is that the two are compared cell by cell against each other on a
known seed, as two living outputs rather than one output and a saved expectation.

The other three exports are not here. The component export and the form
submissions export have a column per product and per form field — a universe is a
fixed, versioned declaration and cannot declare a column for a product that does
not exist yet. The member-changes export builds a narrative per change in some two
hundred lines of Python, which reproducing would mean writing business rules into
the universe, and CR-06 §11 says the universe is a reader. Reported to the master
CLI; no half version of them is seeded here.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "101"
down_revision = "100"
branch_labels = None
depends_on = None


# The columns of `payment.exports.build_payments_export_ods`, in its order. The
# name of the report is the name of its sheet, so the spreadsheet a board member
# opens is titled the same either way.
PAYMENTS_LIST = {
    "key": "payments_list",
    "name": "Betalingen en vorderingen",
    "description": ("Elke vordering en terugbetaling met haar context — dezelfde "
                    "lijst als de exportknop op de betalingenpagina."),
    "selection": {
        "objects": [
            "payment_payable_label", "payment_kind_label", "payment_type_label",
            "payment_method_label", "payment_status_label", "payment_ogm",
            "payment_due", "payment_received", "payment_balance",
            "payment_paid_on", "payment_note",
        ],
        "filters": [],
        "sort": [],
        "layout": "detail",
        "pivot_column": "",
    },
}


def upgrade() -> None:
    bind = op.get_bind()
    tenants = [row[0] for row in bind.execute(sa.text(
        "SELECT id FROM mdm.organizations "
        "WHERE org_type = 'UNIT' AND deleted_at IS NULL ORDER BY id"))]

    for tenant_id in tenants:
        bind.execute(
            sa.text(
                "INSERT INTO reporting.saved_reports "
                "  (tenant_id, name, description, selection, is_shared, builtin_key) "
                "SELECT :t, :n, :d, CAST(:s AS json), TRUE, :k "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM reporting.saved_reports "
                "   WHERE tenant_id = :t AND builtin_key = :k AND deleted_at IS NULL)"
            ),
            {"t": tenant_id, "n": PAYMENTS_LIST["name"],
             "d": PAYMENTS_LIST["description"],
             "s": json.dumps(PAYMENTS_LIST["selection"]),
             "k": PAYMENTS_LIST["key"]},
        )


def downgrade() -> None:
    op.execute("DELETE FROM reporting.saved_reports "
               f"WHERE builtin_key = '{PAYMENTS_LIST['key']}'")

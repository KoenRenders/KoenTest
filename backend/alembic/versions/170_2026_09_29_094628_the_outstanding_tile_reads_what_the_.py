"""The outstanding tile reads what the payments screen shows (#1311).

Koen, 29 September 2026: the payments screen showed an outstanding balance of
€ 102,50, the dashboard € 85. The tile's shipped report `dashboard_outstanding`
counted `payment_amount` — the FULL amount — of payments with the status "In
afwachting". Two differences with the screen, which counts amount minus paid over
every record:

1. a failed online payment did not count. It stays owed until it is paid or
   cancelled; the screen counts it, and Koen: *"op dashboard moet die ook geteld
   worden"*. That was the € 17,50 of the difference;
2. a partly paid charge counted for its whole amount, not for what is still open.

The measure that answers the question already exists: `payment_open_amount`,
amount minus paid, the one outstanding measure since #871. The tile now reads it,
without a status filter.

As migration 115 did for this same report: only a selection that is still the
shipped one is rewritten, so a report a board member adjusted is left alone.
"""

import json

import sqlalchemy as sa
from alembic import op

# The id is a timestamp, not a sequence number (#951). Two CLIs that pick "the
# next number" at the same time pick the same one; two that get a timestamp
# cannot collide. The number at the front of the FILE NAME is there for
# readability only — alembic ignores it, and sorting on it does not give the
# head: two branches can pick the same prefix. The head is what `alembic heads`
# says.
# `repr` with double quotes (#781): the generated file must already be what
# `ruff format` writes, or every new migration turns CI red. A `repr` still, not
# a bare string, because `down_revision` is a tuple for a merge and None for the
# first migration.
revision = "170_2026_09_29_094628"
down_revision = "169_2026_09_29_090415"
branch_labels = None
depends_on = None

BEFORE = {
    "objects": ["payment_amount"],
    "filters": [{"object": "payment_status", "operator": "eq", "values": ["In afwachting"]}],
    "sort": [],
    "layout": "table",
    "pivot_column": "",
}
AFTER = {
    "objects": ["payment_open_amount"],
    "filters": [],
    "sort": [],
    "layout": "table",
    "pivot_column": "",
}


def _rewrite(old: dict, new: dict) -> None:
    """Rewrite the shipped tile report, only where it still carries `old`."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, selection::text FROM reporting.saved_reports "
            "WHERE builtin_key = 'dashboard_outstanding'"
        )
    ).fetchall()
    for row_id, raw in rows:
        if json.loads(raw) != old:
            continue  # adjusted by someone: theirs, not ours
        bind.execute(
            sa.text(
                "UPDATE reporting.saved_reports SET selection = CAST(:s AS json) WHERE id = :i"
            ),
            {"s": json.dumps(new), "i": row_id},
        )


def upgrade() -> None:
    _rewrite(BEFORE, AFTER)


def downgrade() -> None:
    # Restores the shipped selection where it is still the one this migration
    # wrote; a report adjusted since is left alone, as in the upgrade.
    _rewrite(AFTER, BEFORE)

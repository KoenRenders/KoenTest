"""Reporting phase 8 (#849): households per responsible board member.

One shipped report, and it is deliberately a **work list** rather than a number:
households per board member with their membership status, so "which of mine have
not renewed" comes out of the first click. That is what the assignment exists for.

Grouped by board member, membership year and status — the year because a status is
only meaningful within one, and "Niet toegewezen" appears as its own row because a
household without a board member is exactly what somebody wants to see.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "107"
down_revision = "106"
branch_labels = None
depends_on = None


REPORT = {
    "key": "households_per_board_member",
    "name": "Gezinnen per verantwoordelijk bestuurslid",
    "description": ("Welke gezinnen elk bestuurslid draagt, met hun "
                    "lidmaatschapsstatus — de werklijst voor wie nog niet "
                    "hernieuwde."),
    "selection": {
        "objects": ["board_member", "membership_year", "membership_status",
                    "membership_households", "membership_persons"],
        "filters": [{"object": "membership_year", "operator": "eq",
                     "values": [], "symbolic": "dit_jaar"}],
        "sort": [{"object": "board_member", "direction": "asc"}],
        "layout": "table",
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
            {"t": tenant_id, "n": REPORT["name"], "d": REPORT["description"],
             "s": json.dumps(REPORT["selection"]), "k": REPORT["key"]},
        )


def downgrade() -> None:
    op.execute("DELETE FROM reporting.saved_reports "
               f"WHERE builtin_key = '{REPORT['key']}'")

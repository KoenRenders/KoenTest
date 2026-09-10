"""Reporting phase 7 (#848): the six dashboard numbers as saved reports.

One report per tile, each a selection with exactly one measure and no grouping —
so it returns one row with one number, which is what a tile is. The tile reads
that number instead of running its own query.

**Each report reproduces what its tile counts, not what the tile ought to count.**
This moves where a number comes from; it does not change what it means. Where the
existing query counts something narrower or wider than one would guess, the
selection follows the query and the difference is written down here:

- *Leden* counts **every household**, member or not — hence `f_members` and not
  `f_memberships`.
- *Actieve leden* counts membership **rows** with `is_active`, not households, and
  only for the current year. Two households with two active memberships each read
  as four.
- *Leden (personen)* counts people whose membership covers **today**, which is not
  "a membership for this year": somebody joining in October is valid today and
  belongs to next year.
- *Komende activiteiten* counts activities whose **last** day has not passed
  (`end_date`, or `start_date` when there is none).
- *Open taken* counts open tasks **for ADMIN or FINANCE only** — a task for another
  role is not on this tile.
- *Openstaand saldo* sums the amount of records whose status is not paid,
  cancelled or failed. That is a different rule from "charged minus received", and
  the two come apart on a partly paid record.

The four "now" numbers use the relative filter values of #847, so these reports
still answer the question next January.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "107"
down_revision = "106"
branch_labels = None
depends_on = None


DASHBOARD_REPORTS = [
    {
        "key": "dashboard_members",
        "name": "Dashboard — Leden",
        "description": "Alle gezinnen in de administratie, lid of niet.",
        "selection": {"objects": ["member_total_count"], "filters": [],
                      "sort": [], "layout": "table", "pivot_column": ""},
    },
    {
        "key": "dashboard_active_members",
        "name": "Dashboard — Actieve leden",
        "description": "Lidmaatschappen van dit jaar die op actief staan.",
        "selection": {
            "objects": ["membership_active_count"],
            "filters": [{"object": "membership_year", "operator": "eq",
                         "values": [], "symbolic": "dit_jaar"}],
            "sort": [], "layout": "table", "pivot_column": "",
        },
    },
    {
        "key": "dashboard_member_persons",
        "name": "Dashboard — Leden (personen)",
        "description": "Personen van wie het lidmaatschap vandaag geldig is.",
        "selection": {
            "objects": ["membership_person_unique"],
            "filters": [{"object": "membership_person_valid_today",
                         "operator": "eq", "values": ["Ja"]}],
            "sort": [], "layout": "table", "pivot_column": "",
        },
    },
    {
        "key": "dashboard_upcoming_activities",
        "name": "Dashboard — Komende activiteiten",
        "description": "Activiteiten waarvan de laatste dag nog niet voorbij is.",
        "selection": {
            "objects": ["activity_count"],
            "filters": [{"object": "activity_last_date", "operator": "gte",
                         "values": [], "symbolic": "vandaag"}],
            "sort": [], "layout": "table", "pivot_column": "",
        },
    },
    {
        "key": "dashboard_open_tasks",
        "name": "Dashboard — Open taken",
        "description": "Openstaande werkbanktaken voor beheer en penningmeester.",
        "selection": {
            "objects": ["task_count"],
            "filters": [
                {"object": "task_status", "operator": "eq", "values": ["Open"]},
                {"object": "task_role", "operator": "in",
                 "values": ["ADMIN", "FINANCE"]},
            ],
            "sort": [], "layout": "table", "pivot_column": "",
        },
    },
    {
        "key": "dashboard_outstanding",
        "name": "Dashboard — Openstaand saldo",
        "description": "Het bedrag op betaalrecords die nog niet afgehandeld zijn.",
        "selection": {"objects": ["payment_outstanding"], "filters": [],
                      "sort": [], "layout": "table", "pivot_column": ""},
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    tenants = [row[0] for row in bind.execute(sa.text(
        "SELECT id FROM mdm.organizations "
        "WHERE org_type = 'UNIT' AND deleted_at IS NULL ORDER BY id"))]

    for tenant_id in tenants:
        for report in DASHBOARD_REPORTS:
            bind.execute(
                sa.text(
                    "INSERT INTO reporting.saved_reports "
                    "  (tenant_id, name, description, selection, is_shared, builtin_key) "
                    "SELECT :t, :n, :d, CAST(:s AS json), TRUE, :k "
                    "WHERE NOT EXISTS ("
                    "  SELECT 1 FROM reporting.saved_reports "
                    "   WHERE tenant_id = :t AND builtin_key = :k AND deleted_at IS NULL)"
                ),
                {"t": tenant_id, "n": report["name"], "d": report["description"],
                 "s": json.dumps(report["selection"]), "k": report["key"]},
            )


def downgrade() -> None:
    op.execute(
        "DELETE FROM reporting.saved_reports WHERE builtin_key IN ("
        + ", ".join(f"'{r['key']}'" for r in DASHBOARD_REPORTS) + ")"
    )

"""Reporting phase 5 (#841): questions 8, 9 and 10 as saved reports.

With these three the ten questions of CR-06 §3 are complete as a shipped set.
Idempotent per tenant on ``builtin_key``, exactly like the seven of migration 097,
and for the same reason: a board member may have adjusted a shipped report, and a
seed that overwrites his change would be a silent surprise on every deploy.

**Question 8 ships with three dimensions and not four.** §3 names age group,
municipality and household size. Without a year in the report the counts run over
every membership year at once, which is not what "who are our members" means — so
the year is in and household size is one click away in the objects pane. A shipped
report has to be readable on the day it arrives; four dimensions over this data is
a table of merged rows.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "099"
down_revision = "098"
branch_labels = None
depends_on = None


BUILTIN_REPORTS = [
    {
        "key": "member_demographics",
        "name": "Wie zijn onze leden",
        "description": ("Leeftijdsgroep en gemeente per jaar. Groepen van minder "
                        "dan vijf personen worden samengevoegd."),
        "selection": {
            "objects": ["membership_person_year", "person_age_group",
                        "household_municipality", "membership_person_count"],
            "filters": [],
            "sort": [{"object": "membership_person_year", "direction": "desc"}],
            "layout": "table",
            "pivot_column": "",
        },
    },
    {
        "key": "form_usage",
        "name": "Gebruik van de formulieren",
        "description": "Inzendingen per formulier per maand.",
        "selection": {
            "objects": ["form", "date_month", "submission_count"],
            "filters": [],
            "sort": [{"object": "date_month", "direction": "desc"}],
            "layout": "table",
            "pivot_column": "",
        },
    },
    {
        "key": "operations_now",
        "name": "Wat vraagt nu aandacht",
        "description": ("Open taken, mislukte e-mails en betalingen die wachten, "
                        "per ouderdom."),
        "selection": {
            "objects": ["operation_kind", "operation_age_bucket",
                        "operation_count", "operation_age_days"],
            "filters": [],
            "sort": [{"object": "operation_count", "direction": "desc"}],
            "layout": "table",
            "pivot_column": "",
        },
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    tenants = [row[0] for row in bind.execute(sa.text(
        "SELECT id FROM mdm.organizations "
        "WHERE org_type = 'UNIT' AND deleted_at IS NULL ORDER BY id"))]

    for tenant_id in tenants:
        for report in BUILTIN_REPORTS:
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
        + ", ".join(f"'{r['key']}'" for r in BUILTIN_REPORTS) + ")"
    )

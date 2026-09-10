"""Reporting phase 2 (#833): saved reports and the export trail.

CR-06 §5. Two tables in the `reporting` schema and the seed of the seven reports
that ship with the panel, so day one is not an empty screen.

**`saved_reports`** stores a *selection* — which objects, which filters, which
sort — as JSON, never a query. That is what makes a saved report survive a change
to the star: the engine rebuilds the SQL from the universe every time it runs.
`builtin_key` is what makes the seed idempotent and re-runnable for a tenant that
does not exist yet; it is null for everything a person creates.

**`export_log`** is one row per export: who, what, which filters, how many rows.
CR-06 §7.6 asks for this "in the audit domain", and it is not there, deliberately.
The audit domain holds per-row snapshots in each domain's own schema — it has no
table and no schema of its own to put an event in — and the reporting domain may
be imported by nobody, so an audit helper could never call into it. The row
therefore lives with the domain that produces it. Moving it later is a migration,
not a redesign.

Nothing that runs today changes: two new tables in a schema this release created.

**Numbered 099 and hanging off 098, and the whole reporting chain with it.** This
was 097 while it lived on `feature/reporting`; master meanwhile grew its own 097
(platform tenant, #854) and 098 (dropping the reconcile queue, #858) on top of
phase 1. Two migrations with the same revision id is not a merge conflict git can
see — the filenames differ — so it would have arrived on master as a chain alembic
refuses to load. The fourteen migrations of this branch were renumbered to
099-112 before the merge.

Safe because none of them had ever run anywhere: only phase 1 (096) is on master
and on the environments; nothing else was ever deployed. The proof is the "exactly
one head" check, which is why it runs before the merge and not after.
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "099"
down_revision = "098"
branch_labels = None
depends_on = None


# The seven questions of CR-06 §3, as selections over the universe of #832. They
# are the test set the universe had to answer, so they are also the first reports
# it ships with. Each one is exactly what a board member would have composed by
# hand — the point is that he *could* have.
BUILTIN_REPORTS = [
    {
        "key": "members_per_year",
        "name": "Leden per jaar",
        "description": "Hoeveel gezinnen en personen zijn er lid, en hoe verloopt dat per jaar?",
        "selection": {
            "objects": ["membership_year", "membership_households", "membership_persons"],
            "filters": [],
            "sort": [{"object": "membership_year", "direction": "desc"}],
            "layout": "table",
        },
    },
    {
        "key": "membership_flow_per_year",
        "name": "Nieuw, vernieuwd en vervallen per jaar",
        "description": "Hoeveel gezinnen kwamen erbij, hoeveel vernieuwden, hoeveel haakten af?",
        "selection": {
            "objects": ["membership_year", "membership_new", "membership_renewed",
                        "membership_lapsed"],
            "filters": [],
            "sort": [{"object": "membership_year", "direction": "desc"}],
            "layout": "table",
        },
    },
    {
        "key": "registrations_per_activity",
        "name": "Inschrijvingen per activiteit",
        "description": "Welke activiteiten trekken het meeste volk, en hoe verhoudt zich dat tot vorig jaar?",
        "selection": {
            "objects": ["activity_year", "activity", "registration_count",
                        "registration_quantity"],
            "filters": [],
            "sort": [{"object": "registration_quantity", "direction": "desc"}],
            "layout": "table",
        },
    },
    {
        "key": "revenue_per_activity",
        "name": "Opbrengst per activiteit",
        "description": "Wat brengt elke activiteit op: gevorderd, ontvangen, terugbetaald, saldo?",
        "selection": {
            "objects": ["activity", "payment_amount", "payment_amount_paid",
                        "payment_refunded", "payment_open_amount"],
            "filters": [],
            "sort": [{"object": "payment_amount", "direction": "desc"}],
            "layout": "table",
        },
    },
    {
        "key": "revenue_per_month",
        "name": "Omzet per maand",
        "description": "Gevorderd tegenover ontvangen tegenover terugbetaald, per maand.",
        "selection": {
            "objects": ["date_month", "payment_amount", "payment_amount_paid",
                        "payment_refunded"],
            "filters": [],
            "sort": [{"object": "date_month", "direction": "desc"}],
            "layout": "table",
        },
    },
    {
        "key": "outstanding_by_age",
        "name": "Openstaand en hoe lang al",
        "description": "Wat staat er open, per ouderdomsklasse en per soort.",
        "selection": {
            "objects": ["payment_age_bucket", "payment_payable_type",
                        "payment_open_amount", "payment_count"],
            "filters": [],
            "sort": [{"object": "payment_open_amount", "direction": "desc"}],
            "layout": "table",
        },
    },
    {
        "key": "payment_method_per_month",
        "name": "Betaalwijze en betaaltermijn",
        "description": "Hoe betalen mensen — online, overschrijving, cash — en hoe snel?",
        "selection": {
            "objects": ["payment_method", "date_month", "payment_amount",
                        "payment_days_to_paid"],
            "filters": [],
            "sort": [{"object": "date_month", "direction": "desc"}],
            "layout": "table",
        },
    },
]


def upgrade() -> None:
    op.create_table(
        "saved_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        # Null for the reports that ship with the release: they belong to the
        # tenant, not to a person, and nobody should have to hand them over.
        sa.Column("owner_email", sa.String(255), nullable=True),
        sa.Column("selection", sa.JSON(), nullable=False),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default="true"),
        # Stable identifier of a shipped report. Null for everything a person
        # creates; it is what makes the seed below idempotent per tenant.
        sa.Column("builtin_key", sa.String(60), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
        schema="reporting",
    )
    # Partial, on the live rows only: a report someone removed must not block the
    # seed from putting the shipped one back on the next deploy.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_saved_reports_builtin "
        "ON reporting.saved_reports (tenant_id, builtin_key) "
        "WHERE builtin_key IS NOT NULL AND deleted_at IS NULL"
    )

    op.create_table(
        "export_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()"), index=True),
        # The admin's e-mail, like every history table in this code base stores it.
        sa.Column("actor", sa.String(255), nullable=True),
        # dataset · report · ad-hoc
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("saved_report_id", sa.Integer(), nullable=True),
        # The fact key or the report's name — what was taken out.
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        schema="reporting",
    )

    _seed(op.get_bind())


def _seed(bind) -> None:
    """Put the seven reports in every tenant that does not have them yet.

    Idempotent on ``(tenant_id, builtin_key)``, so a re-run changes nothing and a
    tenant added later gets them on the next deploy. It deliberately does NOT
    update a report that is already there: a board member may have adjusted a
    shipped report, and a seed that overwrites his change would be the worst kind
    of surprise — silent, and on every deploy.
    """
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
    op.drop_table("export_log", schema="reporting")
    op.drop_table("saved_reports", schema="reporting")

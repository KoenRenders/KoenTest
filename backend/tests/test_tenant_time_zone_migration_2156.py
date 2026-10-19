"""#2156 — the migration that gives a tenant its time zone and the views its day.

The suite runs migration 316 on the seed only. This test runs the chain to 315 on a database
of its own, writes a workflow task made at 22:30 UTC on 2 October (00:30 on the 3rd in
Brussels), runs 316 and reads what it left:

- `mdm.tenants.time_zone` is there for every tenant, `Europe/Brussels`, NOT NULL;
- the six views that read the database's `CURRENT_DATE` answer with the same columns, in
  the same order and with the same types as before (a replaced view must not change shape);
- the task's own day is the tenant's: `f_tasks.date_key` is 3 October, the UTC cast of the
  old view said 2 October.

Proven red (put back each time): the `created_at::date` cast of `f_tasks` left in the
migration → the date key is the UTC day; a column renamed in one of the six definitions →
the migration refuses or the shape test names the view.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from tests._own_database import own_database

BEFORE = "315_2026_10_19_051425"
AFTER = "316_2026_10_19_095522"

VIEWS = ("d_date", "d_person", "f_members", "f_membership_persons", "f_payments", "f_tasks")


def _shape(conn) -> dict[str, list[tuple[str, str]]]:
    rows = conn.execute(
        text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'reporting' AND table_name = ANY(:views) "
            "ORDER BY table_name, ordinal_position"
        ),
        {"views": list(VIEWS)},
    ).all()
    shape: dict[str, list[tuple[str, str]]] = {}
    for view, column, kind in rows:
        shape.setdefault(view, []).append((column, kind))
    return shape


def test_the_migration_gives_the_tenants_a_zone_and_the_views_the_tenants_day():
    with own_database("tz2156") as (upgrade, engine):
        upgrade(BEFORE)
        with engine.begin() as conn:
            before = _shape(conn)
            conn.execute(
                text(
                    "INSERT INTO workflow.workflow_tasks "
                    "(tenant_id, kind, title, status, subject_type, subject_id, required_role, created_at) "
                    "VALUES (2, 'payment.refund_bevestigen', 'Terugbetaling', 'open', 'payment_record', '1', 'FINANCE', "
                    "'2026-10-02 22:30:00+00')"
                )
            )
            utc_day = conn.execute(
                text("SELECT date_key FROM reporting.f_tasks WHERE tenant_id = 2")
            ).scalar_one()
        assert utc_day == date(2026, 10, 2), "the old view names the UTC day (the fault)"

        upgrade(AFTER)
        with engine.begin() as conn:
            assert [v for v in VIEWS if len(before[v]) == 0] == [], "a view was not found before"
            assert _shape(conn) == before, "a replaced view changed its shape"
            zones = conn.execute(text("SELECT DISTINCT time_zone FROM mdm.tenants")).scalars().all()
            assert zones == ["Europe/Brussels"]
            nullable = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'mdm' AND table_name = 'tenants' AND column_name = 'time_zone'"
                )
            ).scalar_one()
            assert nullable == "NO"
            tenant_day = conn.execute(
                text("SELECT date_key FROM reporting.f_tasks WHERE tenant_id = 2")
            ).scalar_one()
            assert tenant_day == date(2026, 10, 3), "the task belongs to the tenant's day"

"""#2156 — "today" and "the day of a moment" are the tenant's, in the application and in SQL.

Between midnight in Belgium and midnight UTC the application (Brussels) and the database
(`CURRENT_DATE`, UTC) disagreed on what day it is, so a count in Python and one in a
reporting view fell on different days (four parity tests failed in that window).
Now one fact decides both: `mdm.tenants.time_zone`, read by `kernel.clock` and by
`mdm.tenant_today()` / `mdm.tenant_day()`.

What these tests hold:

- the SQL day of a moment equals the application's for every quarter of an hour around
  the two midnights and the two clock changes of 2026, in two zones;
- the SQL `tenant_today()` equals the application's for the same pinned instants (the sweep
  of `tenant_day` above only reads a given moment, not the database's own clock);
- a reporting view asks the tenant's day: with the database's own `now()` pinned inside
  the window (a temporary function that shadows it for the transaction), `d_date` ends
  on the day the application says, and not on the UTC one;
- no reporting view reads the database's own `CURRENT_DATE` or `now()` any more;
- the zone is validated before anything is written, and a new tenant has Brussels.

Broken on purpose (19 October 2026, each put back): `mdm.tenant_day` redefined on UTC →
the sweep of `tenant_day` is red in three zones; `mdm.tenant_today` redefined as
`(now() AT TIME ZONE 'UTC')::date` → the sweep of `tenant_today` and the pinned-view test
are red; `CURRENT_DATE` put back in `f_tasks` → the definition test names the view; the
zone check taken out of `_checked_time_zone` → the refusal test is red; the clock given
back a default tenant → the "no tenant" test is red.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.kernel import clock
from app.kernel.tenancy import current_tenant_id

pytestmark = pytest.mark.ui_agnostisch

BRUSSELS_TENANT = 2


def _tenant(db, code: str, zone: str) -> int:
    """A tenant of its own with a zone, made in the test's transaction (SQL sees it)."""
    return db.execute(
        text(
            "INSERT INTO mdm.tenants (code, kind, account_id, organization_id, is_active, time_zone,"
            " created_at, updated_at)"
            " SELECT :code, kind, account_id, organization_id, true, :zone, now(), now()"
            " FROM mdm.tenants WHERE id = :base RETURNING id"
        ),
        {"code": code, "zone": zone, "base": BRUSSELS_TENANT},
    ).scalar()


def _instants():
    """Every quarter of an hour of the two days around each midnight and the two changes
    of the clock in Brussels in 2026 (29 March, 25 October), and a plain midsummer day."""
    for start in (date(2026, 3, 28), date(2026, 6, 20), date(2026, 10, 24), date(2026, 12, 31)):
        moment = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        for step in range(4 * 24 * 3):
            yield moment + timedelta(minutes=15 * step)


@pytest.mark.parametrize("zone", ["Europe/Brussels", "America/New_York", "Pacific/Auckland"])
def test_the_day_of_a_moment_is_the_same_in_sql_and_in_the_application(
    db_session, monkeypatch, zone
):
    tenant = _tenant(db_session, f"zone-{zone.split('/')[-1].lower()}", zone)
    monkeypatch.setattr(clock, "_zones", {tenant: zone})
    token = current_tenant_id.set(tenant)
    try:
        instants = list(_instants())
        assert len(instants) > 1000, "the sweep looked at too few instants"
        wrong = []
        for instant in instants:
            sql = db_session.execute(
                text("SELECT mdm.tenant_day(:t, :m)"), {"t": tenant, "m": instant}
            ).scalar()
            if sql != clock.belgian_day(instant) or sql != clock.belgian_today(instant):
                wrong.append((instant.isoformat(), sql, clock.belgian_day(instant)))
        assert not wrong, f"SQL and the application disagree on the day, e.g. {wrong[:3]}"
    finally:
        current_tenant_id.reset(token)


def test_the_two_zones_really_differ_in_the_window(db_session):
    """The window the issue is about: 00:30 in Brussels in summer is 22:30 UTC the evening
    before. The sweep above would pass for any zone if all agreed trivially."""
    moment = datetime(2026, 10, 2, 22, 30, tzinfo=timezone.utc)
    assert db_session.execute(
        text("SELECT mdm.tenant_day(:t, :m)"), {"t": BRUSSELS_TENANT, "m": moment}
    ).scalar() == date(2026, 10, 3)
    utc_tenant = _tenant(db_session, "zone-utc", "UTC")
    assert db_session.execute(
        text("SELECT mdm.tenant_day(:t, :m)"), {"t": utc_tenant, "m": moment}
    ).scalar() == date(2026, 10, 2)


def test_a_view_asks_the_tenants_day_not_the_databases(db_session, monkeypatch):
    from tests._pins import pin_database_now

    """The database's own clock pinned at 22:30 UTC on 2 October — 00:30 on the 3rd in
    Brussels — for this transaction only: a function `now()` in a schema of the
    test, first on the search path (the temporary schema is never searched for functions). `d_date` runs two years past "today"; on the old
    `CURRENT_DATE` it would end on the UTC day, and no pin could move it."""

    pinned = datetime(2026, 10, 2, 22, 30, tzinfo=timezone.utc)
    pin_database_now(db_session, pinned)
    try:
        last = db_session.execute(
            text("SELECT max(date_key) FROM reporting.d_date WHERE tenant_id = :t"),
            {"t": BRUSSELS_TENANT},
        ).scalar()
    finally:
        db_session.execute(text("RESET search_path"))
    expected = clock.belgian_today(pinned)
    assert expected == date(2026, 10, 3)
    assert last == expected.replace(year=expected.year + 2), (
        f"d_date ends on {last}: the view did not ask the tenant's day"
    )


def test_no_reporting_view_reads_the_databases_own_date(db_session):
    views = db_session.execute(
        text(
            "SELECT c.relname, pg_get_viewdef(c.oid) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'reporting' AND c.relkind = 'v'"
        )
    ).all()
    assert len(views) >= 10, f"only {len(views)} reporting views found — the walk is blind"
    reading = [
        name
        for name, sql in views
        if "CURRENT_DATE" in sql or "now()" in sql or "CURRENT_TIMESTAMP" in sql
    ]
    assert not reading, f"these views read the database's own clock: {reading}"
    asking = [name for name, sql in views if "tenant_today" in sql or "tenant_day" in sql]
    assert {
        "d_date",
        "d_person",
        "f_members",
        "f_membership_persons",
        "f_payments",
        "f_tasks",
    } <= set(asking), f"the six views that needed the tenant's day: {sorted(asking)}"


def test_a_time_zone_is_validated_before_anything_is_written(db_session):
    from app.domains.mdm.tenant_service import TenantFout, _checked_time_zone

    assert _checked_time_zone(" Europe/Brussels ") == "Europe/Brussels"
    assert _checked_time_zone("America/New_York") == "America/New_York"
    for bad in (
        "",
        "Brussels",
        "Europe/Atlantis",
        "../etc/passwd",
        "europe/brussels "[:0] + "Mars/Base",
    ):
        with pytest.raises(TenantFout):
            _checked_time_zone(bad)


def test_a_tenant_made_without_a_zone_lives_in_brussels(db_session):
    from app.domains.mdm.models import Tenant

    row = db_session.get(Tenant, BRUSSELS_TENANT)
    assert row.time_zone == "Europe/Brussels"
    tenant = _tenant(db_session, "zone-default-probe", "Europe/Brussels")
    assert (
        db_session.execute(
            text("SELECT time_zone FROM mdm.tenants WHERE id = :t"), {"t": tenant}
        ).scalar()
        == "Europe/Brussels"
    )
    # the column default itself, not what a caller passed
    default = db_session.execute(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_schema = 'mdm' AND table_name = 'tenants' AND column_name = 'time_zone'"
        )
    ).scalar()
    assert "Europe/Brussels" in default


# ── The tenant editor and the creation ───────────────────────────────────────


def test_creating_a_tenant_takes_its_zone_or_brussels(db_session):
    from tests._sites import new_site

    plain = new_site(db_session, name="Zonder zone", code="zone-none")
    abroad = new_site(
        db_session, name="Over de oceaan", code="zone-abroad", time_zone="America/New_York"
    )
    db_session.flush()
    assert plain.time_zone == "Europe/Brussels"
    assert abroad.time_zone == "America/New_York"


def test_a_refused_zone_writes_nothing_and_a_saved_one_clears_the_clock(db_session):
    from app.domains.mdm.models import Tenant
    from app.domains.mdm.tenant_service import TenantFout, save_tenant
    from tests._sites import new_site

    tenant = new_site(db_session, name="Zone-editor", code="zone-editor")
    db_session.flush()
    with pytest.raises(TenantFout):
        save_tenant(
            db_session, tenant.id, {}, known=[], secret=[], modules=None, time_zone="Mars/Base"
        )
    db_session.expire_all()
    assert db_session.get(Tenant, tenant.id).time_zone == "Europe/Brussels"

    clock._zones = {tenant.id: "Europe/Brussels"}  # something cached that the save must drop
    save_tenant(
        db_session, tenant.id, {}, known=[], secret=[], modules=None, time_zone="America/New_York"
    )
    assert clock._zones is None, "a changed zone must clear what the clock has read"
    db_session.expire_all()
    assert db_session.get(Tenant, tenant.id).time_zone == "America/New_York"


# ── Today, from the database's clock ─────────────────────────────────────────


@pytest.mark.parametrize("zone", ["Europe/Brussels", "Pacific/Auckland"])
def test_today_in_sql_is_today_in_the_application_for_every_pinned_instant(
    db_session, monkeypatch, zone
):
    from tests._pins import pin_database_now

    tenant = _tenant(db_session, f"today-{zone.split('/')[-1].lower()}", zone)
    monkeypatch.setattr(clock, "_zones", {tenant: zone})
    pin_database_now(db_session)
    wrong = []
    checked = 0
    for instant in list(_instants())[::2]:
        db_session.execute(
            text("SELECT set_config('pin_2156.at', :at, true)"), {"at": instant.isoformat()}
        )
        sql = db_session.execute(text("SELECT mdm.tenant_today(:t)"), {"t": tenant}).scalar()
        checked += 1
        if sql != clock.belgian_today(instant, tenant_id=tenant):
            wrong.append((instant.isoformat(), sql))
    assert checked > 400, "the sweep looked at too few instants"
    assert not wrong, f"SQL's today and the application's disagree, e.g. {wrong[:3]}"


# ── No tenant, no day ────────────────────────────────────────────────────────


def test_the_clock_refuses_a_day_outside_any_tenant(monkeypatch):
    """No default tenant (the architecture CLI's shape, "no silent default"): outside a
    request and outside a job that carries its tenant, the clock says so."""
    monkeypatch.setattr(clock, "tenant_of_the_call", current_tenant_id.get)
    assert current_tenant_id.get() is None
    for ask in (
        clock.belgian_today,
        clock.belgian_now,
        lambda: clock.belgian_day(datetime(2026, 10, 2, 22, 30, tzinfo=timezone.utc)),
    ):
        with pytest.raises(clock.NoTenantContext):
            ask()
    # a caller that has none and means a tenant says so
    assert clock.belgian_today(
        datetime(2026, 10, 2, 22, 30, tzinfo=timezone.utc), tenant_id=2
    ) == date(2026, 10, 3)


def test_a_job_runs_in_the_tenant_it_was_planned_in_and_in_none_otherwise(db_session, monkeypatch):
    from app.kernel.jobs import KernelJob, enqueue, job, run_due_jobs

    seen: dict[str, object] = {}

    @job("probe.2156")
    def probe(db, payload):
        seen["tenant"] = current_tenant_id.get()
        seen["payload_tenant"] = payload.get("tenant_id")
        try:
            clock.belgian_today(tenant_id=None)
        except clock.NoTenantContext as exc:
            seen["clock"] = type(exc).__name__

    monkeypatch.setattr(clock, "tenant_of_the_call", current_tenant_id.get)
    token = current_tenant_id.set(BRUSSELS_TENANT)
    try:
        planned_in = enqueue(db_session, "probe.2156", {})
    finally:
        current_tenant_id.reset(token)
    planned_nowhere = enqueue(db_session, "probe.2156", {})
    db_session.flush()
    assert planned_in.payload == {"tenant_id": BRUSSELS_TENANT}
    assert planned_nowhere.payload == {}, "outside a tenant the job carries none"

    run_due_jobs(db_session)
    first = seen.copy()
    assert first["tenant"] is None and first["clock"] == "NoTenantContext", (
        "a job planned in no tenant runs in none, and the clock says so"
    )
    assert db_session.query(KernelJob).filter_by(name="probe.2156").count() == 2
    assert current_tenant_id.get() is None, "the job's tenant does not leak out of the run"

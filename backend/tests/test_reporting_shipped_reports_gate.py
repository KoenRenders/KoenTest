"""Every shipped report still runs, and still exports (#880).

Koen: *"Heb je ook tests voorzien op de rapporten die je meeleverde? Kwestie dat
ze nog goed werken met de wijzigingen aan het model."* There were tests over
individual reports — the six dashboard numbers, the board member, the address,
the chart — but none that ran **all** of them. The closest one asserted that six
keys exist, which is not the same as those six producing a result.

**Why the gap bites exactly here.** A saved report remembers the **keys** of its
objects, so a rename, a merged class or a removed object makes it point at
something that is no longer there — and that breaks at **run** time, not at build
time. The suite stays green, the migration runs, and the report fails the moment a
board member clicks it. #871 is precisely such a change: if its migration misses
one saved selection, nothing else in this repository notices.

**This is a smoke test, not a value test.** It asserts that a report runs, returns
columns, and exports — never what its numbers should be. Those belong to
`test_reporting_dashboard.py` and the per-report tests, and duplicating them here
would give two places to update and one of them would rot.

**The two ways this gate could be worthless are both covered.**

*It finds nothing and passes.* A missing seed or too strict a filter on
`builtin_key` would loop over zero reports and succeed — #678, exactly. Hence the
minimum count, and hence the count being asserted per tenant rather than overall.

*It does not catch what it exists for.* Broken on purpose: the saved selection of
`members_per_year` was rewritten in the database with `membership_households`
changed to `membership_hoofdlid` — the sort of key a rename leaves behind. The gate
went red naming that report and that key; the row was put back and it went green.
`test_the_gate_goes_red_on_a_renamed_object` reproduces it on every run, so a gate
that only fails on an empty database can never pass for this one.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.domains.reporting.api import (
    SelectionError,
    resolve_selection,
    build_pivot,
    build_pivot_ods,
    build_report_ods,
    list_saved_reports,
    run_validated,
    selection_from_dict,
)
from tests._reporting_seed import TENANT_A, TENANT_B, seed


# Every tenant the seed builds. A report is seeded per tenant, and a tenant whose
# reports were never seeded is its own kind of breakage.
TENANTS = (TENANT_A, TENANT_B)

# What migrations 099 through 113 ship. A number and not a `> 0`: the whole point
# of #678 is that "the loop ran" and "the loop ran over something" are different
# statements.
VERWACHT_AANTAL = 19


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _shipped(db, tenant_id: int):
    return [r for r in list_saved_reports(db, tenant_id=tenant_id, viewer="")
            if r.builtin_key]


def _run(db, rapport, tenant_id: int):
    """Run one saved report the way the panel does.

    Resolving first is not a detail: four of the shipped reports carry a relative
    filter value (#847), and an unresolved "dit jaar" is a filter with no value at
    all. The panel and the export route both resolve before they run, so a test
    that skipped it would fail on something the application never does — and
    would have hidden whatever it was meant to catch.
    """
    selectie = resolve_selection(selection_from_dict(rapport.selection))
    if selectie.layout == "pivot":
        gedraaid = build_pivot(db, selectie, tenant_id=tenant_id)
        return selectie, gedraaid, None
    resultaat = run_validated(db, selectie, tenant_id=tenant_id)
    return selectie, None, resultaat


def test_every_shipped_report_is_seeded_for_every_tenant(db_session, situation):
    """The count first, so the loops below cannot silently run over nothing."""
    for tenant_id in TENANTS:
        rapporten = _shipped(db_session, tenant_id)
        assert len(rapporten) == VERWACHT_AANTAL, (
            f"tenant {tenant_id} heeft {len(rapporten)} meegeleverde rapporten, "
            f"verwacht {VERWACHT_AANTAL} — een rapport dat niet geseed is, is "
            "even stuk als een rapport dat faalt")
        sleutels = [r.builtin_key for r in rapporten]
        assert len(sleutels) == len(set(sleutels)), (
            f"dubbel geseede rapporten in tenant {tenant_id}: {sleutels}")


def test_every_shipped_report_runs_and_returns_columns(db_session, situation):
    """The gate itself: does each one still produce a result?

    Not what the result says — that is the job of the per-report tests. Only that
    the selection still resolves against the universe of today.
    """
    for tenant_id in TENANTS:
        rapporten = _shipped(db_session, tenant_id)
        assert rapporten
        for rapport in rapporten:
            try:
                selectie, gedraaid, resultaat = _run(db_session, rapport, tenant_id)
            except SelectionError as exc:
                raise AssertionError(
                    f"meegeleverd rapport '{rapport.builtin_key}' "
                    f"(tenant {tenant_id}) draait niet meer: {exc}") from exc
            kolommen = (gedraaid.row_columns + gedraaid.measures if gedraaid
                        else resultaat.columns)
            assert kolommen, (
                f"'{rapport.builtin_key}' levert geen kolommen op — een rapport "
                "zonder kolommen is een leeg scherm voor een bestuurder")
            assert len(kolommen) == len(selectie.object_keys), (
                f"'{rapport.builtin_key}' verliest kolommen onderweg: "
                f"{len(kolommen)} van {len(selectie.object_keys)}")


def test_every_shipped_report_exports(db_session, situation):
    """The same loop, through the spreadsheet.

    A missing format (#875) or a column that disappeared bites here just as hard,
    and the export runs code the screen does not — the second sheet with the rows
    behind the result.
    """
    for tenant_id in TENANTS:
        for rapport in _shipped(db_session, tenant_id):
            selectie, gedraaid, resultaat = _run(db_session, rapport, tenant_id)
            try:
                if gedraaid is not None:
                    # `as_context()` like the route does: the ODS builder reads
                    # the plain dict the macro reads, so the sheet and the screen
                    # cannot drift apart.
                    inhoud = build_pivot_ods(db_session, gedraaid.as_context(),
                                             selectie, title=rapport.name,
                                             tenant_id=tenant_id)
                else:
                    inhoud = build_report_ods(db_session, resultaat, selectie,
                                              title=rapport.name,
                                              tenant_id=tenant_id)
            except Exception as exc:  # noqa: BLE001 — any failure is the finding
                raise AssertionError(
                    f"de export van '{rapport.builtin_key}' (tenant {tenant_id}) "
                    f"faalt: {type(exc).__name__}: {exc}") from exc
            assert len(inhoud) > 500, (
                f"de export van '{rapport.builtin_key}' is verdacht klein "
                f"({len(inhoud)} bytes)")


def test_the_gate_goes_red_on_a_renamed_object(db_session, situation):
    """The counter-proof, and it is the one that matters.

    A gate that only fails on an empty database proves nothing about renames —
    and renames are the whole reason this gate exists. So one saved selection is
    rewritten to name an object that does not exist, the way a missed migration
    would leave it.

    What was broken: `members_per_year`, with `membership_households` changed to
    `membership_hoofdlid`. The gate named the report and the key; putting the row
    back made it green.
    """
    rij = db_session.execute(text(
        "SELECT id, selection::text FROM reporting.saved_reports "
        "WHERE builtin_key = 'members_per_year' AND tenant_id = :t"),
        {"t": TENANT_A}).first()
    assert rij, "de seed levert dit rapport"
    origineel = rij[1]
    assert "membership_households" in origineel

    kapot = json.loads(origineel)
    kapot["objects"] = ["membership_hoofdlid" if k == "membership_households"
                        else k for k in kapot["objects"]]
    db_session.execute(text(
        "UPDATE reporting.saved_reports SET selection = CAST(:s AS json) "
        "WHERE id = :id"), {"s": json.dumps(kapot), "id": rij[0]})
    db_session.commit()
    try:
        with pytest.raises(AssertionError) as exc:
            test_every_shipped_report_runs_and_returns_columns(db_session, situation)
        melding = str(exc.value)
        assert "members_per_year" in melding, (
            f"de melding hoort te zeggen wélk rapport stuk is: {melding}")
        assert "membership_hoofdlid" in melding, (
            f"en wélke sleutel niet meer bestaat: {melding}")
    finally:
        db_session.execute(text(
            "UPDATE reporting.saved_reports SET selection = CAST(:s AS json) "
            "WHERE id = :id"), {"s": origineel, "id": rij[0]})
        db_session.commit()

    # And green again, so the repair is part of the proof.
    test_every_shipped_report_runs_and_returns_columns(db_session, situation)


def test_the_gate_would_notice_an_unseeded_tenant(db_session, situation):
    """The other way it could be worthless: looping over nothing (#678)."""
    db_session.execute(text(
        "UPDATE reporting.saved_reports SET deleted_at = NOW() "
        "WHERE tenant_id = :t AND builtin_key IS NOT NULL"), {"t": TENANT_B})
    db_session.commit()
    try:
        with pytest.raises(AssertionError, match="meegeleverde rapporten"):
            test_every_shipped_report_is_seeded_for_every_tenant(db_session,
                                                                 situation)
    finally:
        db_session.execute(text(
            "UPDATE reporting.saved_reports SET deleted_at = NULL "
            "WHERE tenant_id = :t AND builtin_key IS NOT NULL"), {"t": TENANT_B})
        db_session.commit()

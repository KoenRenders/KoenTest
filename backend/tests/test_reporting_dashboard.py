"""The six dashboard numbers, from both sides (#848).

Koen revised principle 8 for this one screen: *"Gelieve in v2.3 de zaken te
voorzien zodat alle bestaande tegels vervangen kunnen worden door Reporting."*
The dashboard stays on `/admin` — it is the landing page of the back office, and
emptying it means a board member has to learn where "the dashboard" lives now. It
becomes a **consumer** of reporting instead of a second implementation.

**This file is the test the issue rests on**, and it only works while both roads
exist: every number is computed the old way and through its saved report, on the
same seed, and they must agree. Running it after the old queries were removed
would prove nothing.

Would it be green if the subject were broken? Each report reproduces what its tile
counts, and several of those are narrower than a reader would guess — open tasks
for two roles only, people valid *today* rather than for this year, an outstanding
balance by status rather than charged-minus-received. Point any of them at the
obvious-looking measure instead and the corresponding assertion fails with two
different numbers.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.domains.reporting.api import (
    list_saved_reports, run_validated, selection_of,
)
from tests._reporting_seed import TENANT_A, seed
from tests.test_reporting_panel_ui import ADMIN_EMAIL, login

# builtin_key -> the key of the one measure the report returns.
TILE_REPORTS = {
    "dashboard_members": "member_total_count",
    "dashboard_active_members": "membership_active_count",
    "dashboard_member_persons": "membership_person_unique",
    "dashboard_upcoming_activities": "activity_count",
    "dashboard_open_tasks": "task_count",
    "dashboard_outstanding": "payment_amount",
}


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _tile_number(db, key: str):
    rapport = next(r for r in list_saved_reports(db, tenant_id=TENANT_A,
                                                 viewer=ADMIN_EMAIL)
                   if r.builtin_key == key)
    resultaat = run_validated(db, selection_of(rapport), tenant_id=TENANT_A,
                              viewer=ADMIN_EMAIL)
    assert len(resultaat.rows) == 1, (
        f"{key} hoort één rij met één getal te geven, een tegel is geen tabel")
    return resultaat.rows[0][TILE_REPORTS[key]]


def _old_stats(db):
    """The dashboard's own query, with the tenant context a request would have.

    `get_stats` has no tenant condition of its own; it leans entirely on the
    ORM's global filter, which the middleware arms per request. That is correct in
    the application and invisible in a test, where the context variable is unset
    and the query quietly counts every tenant. Setting it here is what makes the
    comparison a comparison — and it is worth knowing that the old query has no
    second line of defence if that context is ever missing.
    """
    from app.kernel.tenancy import current_tenant_id
    from app.ui.admin_api import get_stats

    token = current_tenant_id.set(TENANT_A)
    try:
        return get_stats(db=db, _admin=None)  # type: ignore[arg-type]
    finally:
        current_tenant_id.reset(token)


# ── The cross-check (#848, the test the issue rests on) ──────────────────────

def test_every_tile_reads_the_same_number_both_ways(db_session, situation):
    from datetime import datetime, timedelta, timezone

    from app.domains.workflow.api import WorkflowTask

    # A task for each of the two roles the tile counts, and one for a role it does
    # not — otherwise "counts two roles" and "counts everything" look the same.
    nu = datetime.now(timezone.utc)
    for rol in ("ADMIN", "FINANCE", "OPERATOR"):
        db_session.add(WorkflowTask(
            tenant_id=TENANT_A, kind="kernel.job_gefaald", title=f"T {rol}",
            subject_type="kernel_job", subject_id=f"j{rol}", status="open",
            required_role=rol, created_at=nu - timedelta(days=2)))
    db_session.commit()

    oud = _old_stats(db_session)

    assert _tile_number(db_session, "dashboard_members") == oud["members"]
    assert _tile_number(db_session, "dashboard_active_members") == \
        oud["active_members"]
    assert _tile_number(db_session, "dashboard_member_persons") == \
        oud["active_member_persons"]
    assert _tile_number(db_session, "dashboard_upcoming_activities") == \
        oud["upcoming_activities"]
    assert _tile_number(db_session, "dashboard_open_tasks") == oud["open_tasks"]
    assert Decimal(str(_tile_number(db_session, "dashboard_outstanding"))) == \
        Decimal(str(oud["outstanding_balance"]))


def test_the_open_tasks_tile_counts_two_roles_and_not_the_third(db_session,
                                                                situation):
    """The narrowness is the point: a task for OPERATOR is not on this tile."""
    from datetime import datetime, timedelta, timezone

    from app.domains.workflow.api import WorkflowTask

    nu = datetime.now(timezone.utc)
    voor = _tile_number(db_session, "dashboard_open_tasks")
    db_session.add(WorkflowTask(
        tenant_id=TENANT_A, kind="kernel.job_gefaald", title="Alleen operator",
        subject_type="kernel_job", subject_id="jo", status="open",
        required_role="OPERATOR", created_at=nu - timedelta(days=1)))
    db_session.commit()
    assert _tile_number(db_session, "dashboard_open_tasks") == voor, (
        "een taak voor OPERATOR hoort niet op deze tegel")


def test_the_members_tile_counts_a_household_that_never_joined(db_session,
                                                               situation):
    """The grain that was missing: `f_memberships` cannot see this household."""
    from app.domains.mdm.api import Member

    voor = _tile_number(db_session, "dashboard_members")
    db_session.add(Member(tenant_id=TENANT_A))
    db_session.commit()
    assert _tile_number(db_session, "dashboard_members") == voor + 1

    # And it is invisible to the membership fact, which is why the grain was
    # needed at all: distinct households there, against every household here.
    from sqlalchemy import text

    in_lidmaatschappen = db_session.execute(text(
        "SELECT COUNT(DISTINCT member_id) FROM reporting.f_memberships "
        "WHERE tenant_id = :t"), {"t": TENANT_A}).scalar()
    assert in_lidmaatschappen < _tile_number(db_session, "dashboard_members"), (
        "een gezin dat nooit lid was, bestaat niet in f_memberships")


def test_the_persons_tile_follows_validity_and_not_the_year(db_session, situation):
    """The October household is valid today and belongs to next year.

    Counting "members this year" would miss it; the tile counts validity, and so
    does the report. This is the case where the two rules visibly differ.
    """
    from sqlalchemy import text

    vandaag_geldig = _tile_number(db_session, "dashboard_member_persons")
    dit_jaar = db_session.execute(text(
        "SELECT COUNT(*) FROM reporting.f_membership_persons "
        "WHERE tenant_id = :t AND year = EXTRACT(YEAR FROM CURRENT_DATE)"),
        {"t": TENANT_A}).scalar()
    assert vandaag_geldig != dit_jaar, (
        "de seed bevat het oktobergeval, dus de twee regels geven een ander getal")


def test_the_outstanding_tile_uses_the_status_rule(db_session, situation):
    """Charged-minus-received and by-status agree on the seed and must not be
    assumed to agree in general.

    A partly paid record is where they come apart, so this makes one.
    """
    from decimal import Decimal as D

    from app.domains.payment.api import PaymentRecord

    record = db_session.query(PaymentRecord).filter(
        PaymentRecord.status == "pending").first()
    record.amount_paid = D("4.00")
    db_session.commit()

    op_status = D(str(_tile_number(db_session, "dashboard_outstanding")))
    oud = _old_stats(db_session)
    assert op_status == D(str(oud["outstanding_balance"])), (
        "het rapport volgt dezelfde regel als de tegel")

    gevorderd_min_ontvangen = run_validated(
        db_session,
        __import__("app.domains.reporting.api", fromlist=["Selection"]).Selection(
            object_keys=("payment_open_amount",)),
        tenant_id=TENANT_A)
    assert D(str(gevorderd_min_ontvangen.rows[0]["payment_open_amount"])) != op_status, (
        "bij een deels betaald record lopen de twee regels uiteen — dat verschil "
        "is het onderwerp, geen dubbeling")


def test_the_reports_are_shared_and_shipped(db_session, situation):
    keys = {r.builtin_key for r in list_saved_reports(
        db_session, tenant_id=TENANT_A, viewer=ADMIN_EMAIL) if r.builtin_key}
    assert set(TILE_REPORTS) <= keys


def test_a_dashboard_report_still_answers_next_year(db_session, situation):
    """Four of the six are "now" numbers, so they lean on #847.

    Without the relative filter, "Actieve leden" would be a report about 2026
    forever — and this test would be the only place anybody noticed.
    """
    from datetime import date

    rapport = next(r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                                 viewer=ADMIN_EMAIL)
                   if r.builtin_key == "dashboard_active_members")
    selectie = selection_of(rapport)
    assert selectie.filters[0].symbolic == "dit_jaar", (
        "het jaar staat als verwijzing in de bewaarde selectie, niet als jaartal")

    _y0, y1, y2, _y3 = situation["years"]
    vorig = run_validated(db_session, selectie, tenant_id=TENANT_A,
                          today=date(y1, 6, 1))
    dit = run_validated(db_session, selectie, tenant_id=TENANT_A,
                        today=date(y2, 6, 1))
    assert vorig.rows[0]["membership_active_count"] != \
        dit.rows[0]["membership_active_count"]


# ── The screen itself ────────────────────────────────────────────────────────

def test_the_dashboard_shows_six_tiles_that_link_to_their_report(client,
                                                                 db_session,
                                                                 situation):
    """The tile keeps its operational link and gains one to its report.

    Not instead of: at "Open taken" you usually want the workbench, not a table.
    """
    from tests.conftest import SEEDED_ADMIN_EMAIL

    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    pagina = client.get("/admin")
    assert pagina.status_code == 200

    for titel, doel in [("Leden", "/admin/leden"),
                        ("Actieve leden", "/admin/leden"),
                        ("Leden (personen)", "/admin/leden"),
                        ("Komende activiteiten", "/admin/activiteiten"),
                        ("Open taken (werkbank)", "/admin/werkbank"),
                        ("Openstaand saldo", "/admin/betalingen")]:
        assert titel in pagina.text, titel
        assert doel in pagina.text, doel

    assert pagina.text.count("/admin/rapporten/") >= 6, (
        "elke tegel is doorklikbaar naar zijn rapport")


def test_the_dashboard_numbers_are_the_report_numbers(client, db_session,
                                                      situation):
    from tests.conftest import SEEDED_ADMIN_EMAIL

    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    pagina = client.get("/admin")
    for key in ("dashboard_members", "dashboard_member_persons"):
        getal = _tile_number(db_session, key)
        assert f">{getal}<" in pagina.text, f"{key} = {getal} staat op het scherm"

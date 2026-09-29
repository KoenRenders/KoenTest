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

from app.domains.payment.api import PaymentStatus
from app.domains.reporting.api import (
    DASHBOARD_TEGELS,
    list_saved_reports,
    run_validated,
    selection_of,
)
from app.domains.reporting.tests.test_reporting_panel_ui import ADMIN_EMAIL, login
from tests._reporting_seed import TENANT_A, seed

# builtin_key -> the key of the one measure the report returns. Derived from the
# dashboard's own list (#1311): this used to be a copy of it, and a copy of the
# measures is exactly how a test goes on checking the old tile after the tile moved.
TILE_REPORTS = {key: measure for _label, key, measure, _href, _money in DASHBOARD_TEGELS}


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _tile_number(db, key: str):
    rapport = next(
        r
        for r in list_saved_reports(db, tenant_id=TENANT_A, viewer=ADMIN_EMAIL)
        if r.builtin_key == key
    )
    resultaat = run_validated(db, selection_of(rapport), tenant_id=TENANT_A, viewer=ADMIN_EMAIL)
    assert len(resultaat.rows) == 1, (
        f"{key} hoort één rij met één getal te geven, een tegel is geen tabel"
    )
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
        db_session.add(
            WorkflowTask(
                tenant_id=TENANT_A,
                kind="kernel.job_gefaald",
                title=f"T {rol}",
                subject_type="kernel_job",
                subject_id=f"j{rol}",
                status="open",
                required_role=rol,
                created_at=nu - timedelta(days=2),
            )
        )
    db_session.commit()

    oud = _old_stats(db_session)

    assert _tile_number(db_session, "dashboard_members") == oud["members"]
    # #1307: households that are a member today — the member list's KPI, through
    # the same `current_membership_counts`. It used to be compared with
    # `active_members`, membership rows of this year's number: that is the rule
    # the tile had, and the one that lost every renewal after the turnover date.
    assert _tile_number(db_session, "dashboard_active_members") == oud["active_member_households"]
    assert _tile_number(db_session, "dashboard_member_persons") == oud["active_member_persons"]
    assert _tile_number(db_session, "dashboard_upcoming_activities") == oud["upcoming_activities"]
    assert _tile_number(db_session, "dashboard_open_tasks") == oud["open_tasks"]
    assert Decimal(str(_tile_number(db_session, "dashboard_outstanding"))) == Decimal(
        str(oud["outstanding_balance"])
    )


def test_the_open_tasks_tile_counts_two_roles_and_not_the_third(db_session, situation):
    """The narrowness is the point: a task for OPERATOR is not on this tile."""
    from datetime import datetime, timedelta, timezone

    from app.domains.workflow.api import WorkflowTask

    nu = datetime.now(timezone.utc)
    voor = _tile_number(db_session, "dashboard_open_tasks")
    db_session.add(
        WorkflowTask(
            tenant_id=TENANT_A,
            kind="kernel.job_gefaald",
            title="Alleen operator",
            subject_type="kernel_job",
            subject_id="jo",
            status="open",
            required_role="OPERATOR",
            created_at=nu - timedelta(days=1),
        )
    )
    db_session.commit()
    assert _tile_number(db_session, "dashboard_open_tasks") == voor, (
        "een taak voor OPERATOR hoort niet op deze tegel"
    )


def test_the_members_tile_counts_a_household_that_never_joined(db_session, situation):
    """The grain that was missing: `f_memberships` cannot see this household."""
    from app.domains.mdm.api import Member

    voor = _tile_number(db_session, "dashboard_members")
    db_session.add(Member(tenant_id=TENANT_A))
    db_session.commit()
    assert _tile_number(db_session, "dashboard_members") == voor + 1

    # And it is invisible to the membership fact, which is why the grain was
    # needed at all: distinct households there, against every household here.
    from sqlalchemy import text

    in_lidmaatschappen = db_session.execute(
        text("SELECT COUNT(DISTINCT member_id) FROM reporting.f_memberships WHERE tenant_id = :t"),
        {"t": TENANT_A},
    ).scalar()
    assert in_lidmaatschappen < _tile_number(db_session, "dashboard_members"), (
        "een gezin dat nooit lid was, bestaat niet in f_memberships"
    )


def test_the_persons_tile_follows_validity_and_not_the_year(db_session, situation):
    """The October household is valid today and belongs to next year.

    Counting "members this year" would miss it; the tile counts validity, and so
    does the report. This is the case where the two rules visibly differ.
    """
    from sqlalchemy import text

    vandaag_geldig = _tile_number(db_session, "dashboard_member_persons")
    dit_jaar = db_session.execute(
        text(
            "SELECT COUNT(*) FROM reporting.f_membership_persons "
            "WHERE tenant_id = :t AND year = EXTRACT(YEAR FROM CURRENT_DATE)"
        ),
        {"t": TENANT_A},
    ).scalar()
    assert vandaag_geldig != dit_jaar, (
        "de seed bevat het oktobergeval, dus de twee regels geven een ander getal"
    )


def test_the_outstanding_tile_is_the_payments_screens_balance(db_session, situation):
    """#1311: the tile says what the payments screen says — amount minus paid.

    Koen: the screen showed € 102,50, the dashboard € 85. The tile counted the
    full amount of payments "In afwachting": a failed payment fell out (it stays
    owed — *"op dashboard moet die ook geteld worden"*), and a partly paid one
    counted for its whole amount. This used to be the test that held the tile to
    that status rule; it now holds it to the screen, on the three records where
    the two came apart: a failed charge, a partly paid one, and a refund.

    Proven red against master `e9319771`: "payments screen € 58.50, dashboard
    € 45.00" — the failed € 17,50 missing, and the partly paid charge counted
    for its full amount.
    """
    from decimal import Decimal as D

    from app.domains.payment.api import PaymentRecord, aggregate, enriched_records
    from app.kernel.tenancy import current_tenant_id

    pending = (
        db_session.query(PaymentRecord)
        .filter(PaymentRecord.status == PaymentStatus.PENDING, PaymentRecord.tenant_id == TENANT_A)
        .first()
    )
    pending.amount_paid = D("4.00")  # partly paid: open for the rest
    db_session.add(
        PaymentRecord(
            tenant_id=TENANT_A,
            payable_type=pending.payable_type,
            payable_id=pending.payable_id,
            amount=D("17.50"),
            method="online",
            status=PaymentStatus.FAILED,
        )
    )
    db_session.commit()
    assert db_session.query(PaymentRecord).filter(PaymentRecord.type == "refund").count(), (
        "the seed lost its refund — this test needs one"
    )

    token = current_tenant_id.set(TENANT_A)
    try:
        screen = aggregate(enriched_records(db_session))["saldo"]
    finally:
        current_tenant_id.reset(token)
    tile = D(str(_tile_number(db_session, "dashboard_outstanding")))

    assert tile == screen, f"payments screen € {screen}, dashboard € {tile}"
    assert D(str(_old_stats(db_session)["outstanding_balance"])) == screen


def test_the_reports_are_shared_and_shipped(db_session, situation):
    keys = {
        r.builtin_key
        for r in list_saved_reports(db_session, tenant_id=TENANT_A, viewer=ADMIN_EMAIL)
        if r.builtin_key
    }
    assert set(TILE_REPORTS) <= keys


def test_a_dashboard_report_still_answers_next_year(db_session, situation):
    """The "now" numbers lean on #847.

    Without the relative filter, "Komende activiteiten" would be a report about one
    day forever — and this test would be the only place anybody noticed. (It used
    "Actieve leden", whose year filter went with #1307: that tile now asks which
    households are a member today, as the persons tile does.)
    """
    from datetime import date

    rapport = next(
        r
        for r in list_saved_reports(db_session, tenant_id=TENANT_A, viewer=ADMIN_EMAIL)
        if r.builtin_key == "dashboard_upcoming_activities"
    )
    selectie = selection_of(rapport)
    assert selectie.filters[0].symbolic == "vandaag", (
        "de dag staat als verwijzing in de bewaarde selectie, niet als datum"
    )

    y0, _y1, _y2, y3 = situation["years"]
    vorig = run_validated(db_session, selectie, tenant_id=TENANT_A, today=date(y0, 1, 1))
    later = run_validated(db_session, selectie, tenant_id=TENANT_A, today=date(y3 + 1, 1, 1))
    assert vorig.rows[0]["activity_count"] != later.rows[0]["activity_count"]


# ── The screen itself ────────────────────────────────────────────────────────


def test_the_dashboard_shows_six_tiles_that_link_to_their_report(client, db_session, situation):
    """The tile keeps its operational link and gains one to its report.

    Not instead of: at "Open taken" you usually want the workbench, not a table.
    """
    from tests.conftest import SEEDED_ADMIN_EMAIL

    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    pagina = client.get("/admin")
    assert pagina.status_code == 200

    for titel, doel in [
        ("Leden", "/admin/leden"),
        ("Actieve gezinnen", "/admin/leden"),
        ("Personen (actief lid)", "/admin/leden"),
        ("Komende activiteiten", "/admin/activiteiten"),
        ("Open taken (werkbank)", "/admin/werkbank"),
        ("Openstaand saldo", "/admin/betalingen"),
    ]:
        assert titel in pagina.text, titel
        assert doel in pagina.text, doel

    assert pagina.text.count("/admin/rapporten/") >= 6, (
        "elke tegel is doorklikbaar naar zijn rapport"
    )


def test_the_dashboard_numbers_are_the_report_numbers(client, db_session, situation):
    from tests.conftest import SEEDED_ADMIN_EMAIL

    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    pagina = client.get("/admin")
    for key in ("dashboard_members", "dashboard_member_persons"):
        getal = _tile_number(db_session, key)
        assert f">{getal}<" in pagina.text, f"{key} = {getal} staat op het scherm"


def test_dashboard_numbers_resolves_every_tile_on_the_one_clock(db_session, situation):
    """Wave 7 (#913, B3): `dashboard_numbers` takes `today` and threads it into
    every tile's `run_validated`. Without it each tile resolved its own clock,
    and around midnight six tiles could disagree. Proven the same way as the
    next-year test above: the same call with two clocks gives two answers."""
    from datetime import date

    from app.domains.reporting.api import dashboard_numbers

    y0, _y1, _y2, y3 = situation["years"]
    wanted = [("dashboard_upcoming_activities", "activity_count")]
    vorig = dashboard_numbers(
        db_session, wanted, tenant_id=TENANT_A, viewer=ADMIN_EMAIL, today=date(y0, 1, 1)
    )
    later = dashboard_numbers(
        db_session, wanted, tenant_id=TENANT_A, viewer=ADMIN_EMAIL, today=date(y3 + 1, 1, 1)
    )
    assert (
        vorig["dashboard_upcoming_activities"].value != later["dashboard_upcoming_activities"].value
    )


def test_the_dashboard_names_its_peilmoment(client, db_session, situation):
    """Wave 7 (#913, B3): the screen says what moment its numbers are from —
    the same single clock the tiles resolved on."""
    from tests.conftest import SEEDED_ADMIN_EMAIL

    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    pagina = client.get("/admin")
    assert "Cijfers van" in pagina.text

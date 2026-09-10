"""The remaining facts, the threshold, and questions 8 to 10 (#841).

Three things are worth a test here and they are not equally obvious. The facts
have known numbers, like every fact since #832. `f_tasks` is the workbench and
nothing else — it used to be a union over three domains and counted the same
problem twice — so its interesting property is that a problem appears once, under
the kind of task it produced. And the small-cell threshold is a privacy rule,
which means it has to be checked from both sides: a group of four must not
appear, a group of five must, and the numbers must still add up afterwards —
otherwise a reader distrusts the total instead of realising something was folded.

Would these be green if the subject were broken? Drop the `status = 'open'` from
the workbench leg and the operations count rises; lower the threshold to four and
the merge test fails on the group of four; make the merge drop rows instead of
folding them and the "still adds up" test fails.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.domains.reporting.api import (
    MERGED_LABEL, SMALL_CELL_THRESHOLD, Filter, Operator, Selection,
    list_saved_reports, run_validated, selection_of,
)
from tests._reporting_seed import TENANT_A, TENANT_B, seed
from tests.test_reporting_panel_ui import ADMIN_EMAIL, login


def run(db, keys, *, tenant=TENANT_A, filters=()):
    return run_validated(
        db, Selection(object_keys=tuple(keys), filters=tuple(filters), limit=5000),
        tenant_id=tenant)


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _operations(db, *, tenant=TENANT_A):
    """Two open workbench tasks and one that is done.

    The kinds are the real ones the sweep produces: a refund waiting for FINANCE
    and a mail that failed for good. Both come with the row they are *about* —
    the failed mail in the log — because the point of one of the tests below is
    that the report shows one problem once, not twice.
    """
    from app.domains.mail.api import EmailLog
    from app.domains.workflow.api import WorkflowTask

    nu = datetime.now(timezone.utc)
    db.add(WorkflowTask(tenant_id=tenant, kind="payment.refund_bevestigen",
                        title="Refund bevestigen", subject_type="payment_record",
                        subject_id="abc", status="open", required_role="FINANCE",
                        created_at=nu - timedelta(days=3)))
    db.add(WorkflowTask(tenant_id=tenant, kind="mail.definitief_gefaald",
                        title="E-mail definitief gefaald", subject_type="email_log",
                        subject_id="1", status="open", required_role="ADMIN",
                        created_at=nu - timedelta(days=10)))
    db.add(WorkflowTask(tenant_id=tenant, kind="kernel.job_gefaald", title="Klaar",
                        subject_type="kernel_job", subject_id="def", status="done",
                        required_role="ADMIN", created_at=nu - timedelta(days=40)))
    # The mail behind that second task, plus one that was skipped and one that was
    # logged — both of which are normal states and must not read as problems.
    db.add(EmailLog(tenant_id=tenant, recipient="iemand@example.com",
                    subject="Bevestiging", email_type="registration",
                    status="failed", error_message="smtp",
                    created_at=nu - timedelta(days=10)))
    db.add(EmailLog(tenant_id=tenant, recipient="iemand@example.com",
                    subject="Bevestiging", email_type="registration",
                    status="skipped", created_at=nu - timedelta(days=10)))
    db.add(EmailLog(tenant_id=tenant, recipient="iemand@example.com",
                    subject="Bevestiging", email_type="registration",
                    status="logged", created_at=nu - timedelta(days=10)))
    db.commit()


# ── f_tasks: the workbench, and only the workbench ──────────────────────────
#
# The fact was a union over three tables until it turned out to count the same
# problem twice: a definitively failed mail and a refund awaiting confirmation are
# workbench *task kinds*, so they were in the task leg and again in their own leg.
# The three things #841 names are three kinds, not three tables. Migration 102
# reduced it to the workbench; 103 renamed it to `f_tasks` — the old name promised
# a scope it no longer had, and a promise like that invites the next reader to put
# the mail leg back — and made status a dimension instead of a filter baked into
# the view. These tests hold both.
#
# They assert a DELTA and not a total, and that is not laziness. The mail log is
# written by dozens of other tests through their own session, so an absolute count
# over a tenant is a claim about everything the suite left behind — it read 214
# rows where this fixture adds one.

def _per_kind(db, *, tenant=TENANT_A, status="Open") -> dict[str, int]:
    """Tasks per kind. The status is a FILTER now, not a property of the fact."""
    filters = [Filter("task_status", Operator.EQ, (status,))] if status else []
    result = run(db, ["task_kind", "task_count"], tenant=tenant, filters=filters)
    return {row["task_kind"]: row["task_count"] for row in result.rows}


def _open_count(db, *, tenant=TENANT_A) -> int:
    result = run(db, ["task_count"], tenant=tenant,
                 filters=[Filter("task_status", Operator.EQ, ("Open",))])
    return result.rows[0]["task_count"] if result.rows else 0


def _delta(voor: dict[str, int], na: dict[str, int]) -> dict[str, int]:
    return {soort: na.get(soort, 0) - voor.get(soort, 0)
            for soort in set(voor) | set(na)
            if na.get(soort, 0) != voor.get(soort, 0)}


def test_the_kinds_are_the_task_kinds(db_session, situation):
    """A problem shows up once, under the kind of task it produced."""
    voor = _per_kind(db_session)
    _operations(db_session)

    assert _delta(voor, _per_kind(db_session)) == {
        "Terugbetaling bevestigen": 1,
        "E-mail definitief mislukt": 1,
    }, "twee open taken erbij, elk onder haar eigen soort"


def test_a_failed_mail_is_one_problem_and_not_two(db_session, situation):
    """The double count that migration 102 removed, pinned so it cannot return.

    The fixture writes one failed mail AND the task the sweep makes for it. The
    report must show one row. Before 102 it showed two: one as "Open taak" and one
    as "Mislukte e-mail", and both looked entirely reasonable.
    """
    voor = _open_count(db_session)
    _operations(db_session)
    assert _open_count(db_session) - voor == 2, (
        "twee open taken, niet vier: de mail en de refund tellen één keer")


def test_a_skipped_or_logged_mail_is_not_a_problem(db_session, situation):
    """The other half of the same mistake, and the one that would have been seen.

    `skipped` and `logged` are normal states — `logged` is exactly what a tenant
    configured to log instead of send does with every message. The old mail leg
    read `status <> 'sent'` and would have shown a board member 225 "problems" on
    an afdeling that simply does not send mail.
    """
    _operations(db_session)
    niet_verzonden = db_session.execute(text(
        "SELECT COUNT(*) FROM mail.email_log "
        "WHERE tenant_id = :t AND status <> 'sent'"), {"t": TENANT_A}).scalar()
    assert niet_verzonden >= 3, "de fixture zet er failed, skipped én logged in"

    open_items = _open_count(db_session)
    assert open_items < niet_verzonden, (
        "de werkvoorraad telt taken, niet elke mail die niet verzonden is")


def test_a_finished_task_is_not_an_open_item(db_session, situation):
    """The fixture adds three tasks; one of them is done."""
    voor = _per_kind(db_session)
    _operations(db_session)
    na = _per_kind(db_session)
    assert "Achtergrondtaak mislukt" not in _delta(voor, na), (
        "de afgehandelde taak hoort niet in de werkvoorraad")


def test_operations_stay_inside_their_tenant(db_session, situation):
    """A task belongs to a tenant, and the fact filters on it."""
    voor_a = _per_kind(db_session)
    voor_b = _per_kind(db_session, tenant=TENANT_B)
    _operations(db_session, tenant=TENANT_B)

    assert _delta(voor_a, _per_kind(db_session)) == {}, (
        "wat in tenant B gebeurt, verschijnt niet bij tenant A")
    assert _delta(voor_b, _per_kind(db_session, tenant=TENANT_B)) == {
        "Terugbetaling bevestigen": 1, "E-mail definitief mislukt": 1}


# ── f_form_submissions ───────────────────────────────────────────────────────

def _submissions(db, aantal: int, *, tenant=TENANT_A):
    from app.domains.forms.api import Form as FormModel
    from app.domains.forms.api import FormSubmission

    formulier = FormModel(tenant_id=tenant, title="Testformulier",
                          share_token=f"tok-{tenant}-{aantal}", status="open")
    db.add(formulier)
    db.flush()
    for index in range(aantal):
        db.add(FormSubmission(tenant_id=tenant, form_id=formulier.id,
                              submitter_email=f"x{index}@example.com"))
    db.commit()
    return formulier


def test_submissions_are_counted_per_form(db_session, situation):
    """Per form, so other forms in the database cannot change the answer."""
    formulier = _submissions(db_session, 3)
    result = run(db_session, ["form", "submission_count"])
    per_formulier = {row["form"]: row["submission_count"] for row in result.rows}
    assert per_formulier.get(formulier.title) == 3


def test_a_submission_carries_no_name_or_e_mail(db_session):
    kolommen = {row[0] for row in db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'reporting' AND table_name = 'f_form_submissions'"))}
    assert "submitter_name" not in kolommen
    assert "submitter_email" not in kolommen
    assert "has_contact" in kolommen, "dát er een contact was, mag wel"


# ── f_membership_persons and question 8 ──────────────────────────────────────

def test_a_person_in_two_households_counts_once(db_session, situation):
    """"How many members do we have" must not count anybody twice."""
    from app.domains.mdm.api import MemberPerson

    _y0, _y1, y2, _y3 = situation["years"]
    # Put H1's head of family in H3 as well, for the same year.
    persoon = db_session.execute(text(
        "SELECT person_id FROM mdm.member_persons WHERE member_id = :m LIMIT 1"),
        {"m": situation["households"]["h1"]}).scalar()
    db_session.add(MemberPerson(tenant_id=TENANT_A,
                                member_id=situation["households"]["h3"],
                                person_id=persoon, relation_type="PARTNER"))
    db_session.commit()

    aantal = db_session.execute(text(
        "SELECT COUNT(*) FROM reporting.f_membership_persons "
        "WHERE tenant_id = :t AND year = :y AND person_id = :p"),
        {"t": TENANT_A, "y": y2, "p": persoon}).scalar()
    assert aantal == 1, "één rij per persoon per jaar, ook bij twee gezinnen"


# ── The small-cell threshold (#841 test 2) ───────────────────────────────────

def test_a_group_of_four_is_merged_and_a_group_of_five_is_not(db_session,
                                                              situation):
    """The rule from both sides — and the counter-proof is the group of five.

    Without it, a threshold that folded everything and a threshold that works
    would look the same from the green side.
    """
    from datetime import date

    from app.domains.mdm.api import Member, MemberPerson, Person
    from app.domains.membership.api import Membership

    _y0, _y1, y2, _y3 = situation["years"]
    geboren = date(y2 - 30, 6, 15)

    def gezin(personen: int, gemeente_pc: str) -> None:
        from app.domains.mdm.api import Address, PostalCode

        pc = PostalCode(postal_code=gemeente_pc, municipality=f"Plaats{gemeente_pc}")
        db_session.add(pc)
        db_session.flush()
        member = Member(tenant_id=TENANT_A)
        db_session.add(member)
        db_session.flush()
        for index in range(personen):
            person = Person(tenant_id=TENANT_A, first_name=f"P{index}",
                            last_name="Test", date_of_birth=geboren, gender_code="M")
            db_session.add(person)
            db_session.flush()
            db_session.add(MemberPerson(
                tenant_id=TENANT_A, member_id=member.id, person_id=person.id,
                relation_type="HOOFDLID" if index == 0 else "PARTNER"))
            if index == 0:
                db_session.add(Address(tenant_id=TENANT_A, person_id=person.id,
                                       street="Straat", house_number="1",
                                       postal_code_id=pc.id))
        db_session.add(Membership(tenant_id=TENANT_A, member_id=member.id,
                                  year=y2, is_active=True))
        db_session.commit()

    gezin(4, "1111")   # under the threshold
    gezin(5, "2222")   # exactly at it

    result = run(db_session, ["member_municipality", "membership_person_count"],
                 filters=[Filter("membership_person_year", Operator.EQ, (str(y2),))])
    per_gemeente = {row["member_municipality"]: row["membership_person_count"]
                    for row in result.rows}

    assert "Plaats2222" in per_gemeente, "vijf personen: een eigen cel"
    assert per_gemeente["Plaats2222"] == 5
    assert "Plaats1111" not in per_gemeente, "vier personen: geen eigen cel"
    assert MERGED_LABEL in per_gemeente, "ze zijn samengevoegd, niet weggegooid"

    # And it still adds up: the totals row comes from SQL over the whole set.
    som = sum(row["membership_person_count"] for row in result.rows
              if row["membership_person_count"] is not None)
    assert som == result.totals["membership_person_count"], (
        "de som van de buckets blijft gelijk aan het totaal, ook mét samenvoeging")


def test_the_threshold_only_fires_on_a_sensitive_dimension(db_session, situation):
    """Grouping by year is not grouping people into recognisable groups."""
    result = run(db_session, ["membership_person_year", "membership_person_count"])
    assert MERGED_LABEL not in {row["membership_person_year"] for row in result.rows}
    assert all(row["membership_person_count"] for row in result.rows)


def test_a_non_additive_measure_stays_empty_in_the_merged_row(db_session,
                                                              situation):
    """An average of averages is not an average, so the merged cell shows nothing.

    A number there would look right and be wrong — the exact failure the whole
    "ask SQL, never add up" rule exists to prevent. Payments per municipality is
    chosen because it puts both kinds of measure in one report: an amount, which
    adds up over merged groups, and a distinct count, which does not.

    Deliberately not written with a `skip` if no cell is small: a test that can
    quietly do nothing is worse than no test, because it reads as coverage.
    """
    result = run(db_session, ["member_municipality", "payment_amount",
                              "payment_count"])
    samengevoegd = [row for row in result.rows
                    if row["member_municipality"] == MERGED_LABEL]
    assert samengevoegd, (
        "elk gezin in de seed is klein, dus er hoort een samengevoegde rij te zijn")

    assert samengevoegd[0]["payment_count"] is None, (
        "COUNT(DISTINCT) is niet optelbaar over samengevoegde groepen")
    assert Decimal(samengevoegd[0]["payment_amount"]) > 0, (
        "een SUM is dat wel, en die blijft dus staan")


def test_the_threshold_is_declared_and_not_hidden_in_a_template():
    """#841: the rule lives in the universe declaration, not in a screen."""
    from pathlib import Path

    from app.domains.reporting.api import OBJECTS

    gevoelig = {o.key for o in OBJECTS if o.sensitive}
    assert {"person_age_group", "member_municipality", "member_size_group"} \
        <= gevoelig
    assert SMALL_CELL_THRESHOLD == 5

    sjablonen = Path(__file__).resolve().parents[1] / "app" / "domains" / "reporting" \
        / "templates"
    for pad in sjablonen.glob("*.html"):
        tekst = pad.read_text(encoding="utf-8")
        assert "minder dan 5" not in tekst.lower(), (
            f"{pad.name} kent de drempel — die hoort in de declaratie")


# ── Questions 8, 9 and 10 as shipped reports (#841 test 1) ───────────────────

def test_the_ten_questions_are_now_complete(db_session, situation):
    """The ten of CR-06 §3, as shipped reports.

    Asserted as a subset and then as an exact set, so a new shipped report is a
    visible change here instead of a silent one: the payments listing of #841
    point 4 is the eleventh and is deliberately NOT one of the ten questions.
    """
    reports = {r.builtin_key for r in
               list_saved_reports(db_session, tenant_id=TENANT_A,
                                  viewer=ADMIN_EMAIL) if r.builtin_key}
    tien_vragen = {
        "members_per_year", "membership_flow_per_year",
        "registrations_per_activity", "revenue_per_activity", "revenue_per_month",
        "outstanding_by_age", "payment_method_per_month",
        "member_demographics", "form_usage", "operations_now",
    }
    assert tien_vragen <= reports, "de tien bestuurdersvragen zijn compleet"
    dashboard = {"dashboard_members", "dashboard_active_members",
                 "dashboard_member_persons", "dashboard_upcoming_activities",
                 "dashboard_open_tasks", "dashboard_outstanding"}
    assert reports == tien_vragen | dashboard | {"payments_list",
                                                 "households_per_board_member"}, (
        "en daarnaast de betalingenlijst (#841 punt 4), de zes dashboardtegels "
        "(#848) en de werklijst per bestuurslid (#849) — geen van die is een "
        "bestuurdersvraag uit §3")


def test_the_three_new_reports_run_and_return_the_seed_s_numbers(db_session,
                                                                 situation):
    _operations(db_session)
    formulier = _submissions(db_session, 3)

    reports = {r.builtin_key: r for r in
               list_saved_reports(db_session, tenant_id=TENANT_A,
                                  viewer=ADMIN_EMAIL) if r.builtin_key}

    gebruik = run_validated(db_session, selection_of(reports["form_usage"]),
                            tenant_id=TENANT_A)
    per_formulier = {row["form"]: row["submission_count"] for row in gebruik.rows}
    assert per_formulier.get(formulier.title) == 3

    aandacht = run_validated(db_session, selection_of(reports["operations_now"]),
                             tenant_id=TENANT_A)
    soorten = {row["task_kind"] for row in aandacht.rows}
    assert {"Terugbetaling bevestigen", "E-mail definitief mislukt"} <= soorten

    wie = run_validated(db_session, selection_of(reports["member_demographics"]),
                        tenant_id=TENANT_A)
    assert wie.rows, "het demografierapport draait"
    # Every household in the seed is small, so everything folds into one row —
    # which is what the threshold is for, and the total still holds.
    assert wie.totals["membership_person_count"] > 0


def test_the_new_reports_show_up_in_the_panel(client, db_session, situation):
    _operations(db_session)
    login(client, db_session)
    lijst = client.get("/admin/rapporten")
    for naam in ("Wie zijn onze leden", "Gebruik van de formulieren",
                 "Wat vraagt nu aandacht"):
        assert naam in lijst.text, naam

    reports = {r.builtin_key: r for r in
               list_saved_reports(db_session, tenant_id=TENANT_A,
                                  viewer=ADMIN_EMAIL) if r.builtin_key}
    paneel = client.get(f"/admin/rapporten/{reports['operations_now'].id}")
    assert paneel.status_code == 200
    assert "Terugbetaling bevestigen" in paneel.text

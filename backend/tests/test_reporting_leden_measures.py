"""The Leden measures after #871, and the status that became a dimension.

Koen, on HDEV: *"Bij leden vind ik de measures moeilijk te onderscheiden."* The
fault underneath was that a filter had crept into the name of a measure. A measure
answers *how many*; *which of them* is a dimension. Put the condition in the name
and you get two measures that differ only in something the reader cannot see —
which is precisely why they could not be told apart.

**The hard requirement is that no number moves.** `test_reporting_dashboard.py`
checks every tile along both roads; this file checks the rest: that the status
really is a dimension, that the conversion of the flow report keeps its three
numbers, and that the payments tile survived losing the measure it read.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.domains.reporting.api import (Filter, Operator, Selection, BY_KEY,
                                       run_validated)
from tests._reporting_seed import TENANT_A, seed


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _total(db, key: str, filters=()) -> int:
    return run_validated(db, Selection(object_keys=(key,), filters=tuple(filters)),
                         tenant_id=TENANT_A).rows[0][key]


def test_grouping_on_the_status_adds_up_to_the_unfiltered_count(db_session,
                                                                situation):
    """The test that proves the status is a dimension and not three measures.

    A dimension partitions: every household-year sits in exactly one status, so
    the groups must add up to the whole. Three measures under different names
    carry no such guarantee — they could overlap or leave a gap and nothing would
    notice.

    **Per year, and that is not a workaround.** The status is a property of a
    household-year: a household is new in one year and renewed in the next, so
    across years it appears in more than one status and the totals are not meant
    to add up. Within a year they are, and that is where the partition lives.
    """
    per_jaar = {r["membership_year"]: r["membership_count"] for r in run_validated(
        db_session, Selection(object_keys=("membership_year", "membership_count")),
        tenant_id=TENANT_A).rows}
    per_status: dict[int, int] = {}
    rijen = run_validated(
        db_session,
        Selection(object_keys=("membership_year", "membership_status",
                               "membership_count")),
        tenant_id=TENANT_A).rows
    for rij in rijen:
        per_status[rij["membership_year"]] = (
            per_status.get(rij["membership_year"], 0) + rij["membership_count"])
    assert per_status == per_jaar, (
        f"per status {per_status} telt niet op tot per jaar {per_jaar}")
    assert len({r["membership_status"] for r in rijen}) > 1, (
        "anders toetst de optelling niets")


def test_every_household_year_lands_in_a_named_status(db_session, situation):
    """The gate, and it is not the one the issue asked for.

    The issue asked for "grouping on the status adds up to the unfiltered count,
    broken by leaving a status value out". I tried that, and it cannot go red: the
    join to the code list is a LEFT JOIN, so a missing entry does not drop the
    rows — it gives them an **empty label**. The sum stays right while the report
    grows a nameless group, which is the more dangerous failure of the two,
    because a total that still adds up looks correct.

    So the gate is that every household-year carries a status a person can read.

    **Broken once, on purpose.** `d_membership_status` was rebuilt without its
    LAPSED row. The sum per status stayed exactly equal to the count per year —
    proving the issue's version of this gate could never fail — while three
    household-years came back with an empty status label, and this test named
    them. The code list was put back and it went green.
    """
    def naamloos() -> int:
        return sum(r["membership_count"] for r in run_validated(
            db_session,
            Selection(object_keys=("membership_year", "membership_status",
                                   "membership_count")),
            tenant_id=TENANT_A).rows
            if not (r["membership_status"] or "").strip())

    assert naamloos() == 0, (
        "elk gezinsjaar hoort een leesbare status te dragen; een lege komt van "
        "een ontbrekende rij in d_membership_status en valt in een rapport niet op")

    zonder_lapsed = (
        "CREATE OR REPLACE VIEW reporting.d_membership_status AS "
        "SELECT o.id AS tenant_id, v.code, v.label, v.sort_order "
        "FROM mdm.organizations o "
        "CROSS JOIN (VALUES ('NEW', 'Nieuw', 1), ('RENEWED', 'Vernieuwd', 2)) "
        "  AS v(code, label, sort_order) "
        "WHERE o.org_type = 'UNIT' AND o.deleted_at IS NULL")
    volledig = zonder_lapsed.replace(
        "('RENEWED', 'Vernieuwd', 2)",
        "('RENEWED', 'Vernieuwd', 2), ('LAPSED', 'Vervallen', 3)")
    db_session.execute(text(zonder_lapsed))
    db_session.commit()
    try:
        assert naamloos() > 0, (
            "met een ontbrekende statuswaarde horen er gezinsjaren zonder "
            "leesbare status te zijn — zijn die er niet, dan bewijst deze gate "
            "niets")
    finally:
        db_session.execute(text(volledig))
        db_session.commit()
    assert naamloos() == 0, "en hersteld is hij weer groen"


def test_the_member_count_correctly_reports_no_lapsed_members(db_session,
                                                              situation):
    """Why the flow report counts households and not members.

    A lapsed household has no membership that year, so "Aantal leden (hoofdlid)"
    is zero for it — rightly. That is the one number question 2 of CR-06 exists to
    produce, so the conversion had to pick the other measure. Pinned here, because
    it is the kind of subtlety a later edit undoes by "simplifying".
    """
    rijen = {r["membership_status"]: r for r in run_validated(
        db_session,
        Selection(object_keys=("membership_status", "membership_households",
                               "membership_count")),
        tenant_id=TENANT_A).rows}
    assert rijen["Vervallen"]["membership_households"] == 0
    assert rijen["Vervallen"]["membership_count"] > 0


def test_active_is_a_filter_now_and_the_tile_number_holds(db_session, situation):
    """"How many active" is a count with a visible filter."""
    actief = run_validated(
        db_session,
        Selection(object_keys=("membership_year", "membership_is_active",
                               "membership_count")),
        tenant_id=TENANT_A).rows
    labels = {r["membership_is_active"] for r in actief}
    assert labels <= {"Ja", "Nee"} and labels

    per_jaar = sum(r["membership_count"] for r in run_validated(
        db_session, Selection(object_keys=("membership_year", "membership_count")),
        tenant_id=TENANT_A).rows)
    assert sum(r["membership_count"] for r in actief) == per_jaar


def test_the_payment_status_code_list_is_still_complete(db_session, situation):
    """The closed-world assumption the outstanding tile now rests on (#871).

    The tile summed `amount` where the status is not paid, cancelled or failed.
    Over a list of exactly four codes that is "pending", so it became a measure
    plus a visible filter. A fifth status would make those two diverge silently —
    so it fails here instead.
    """
    codes = {row[0] for row in db_session.execute(text(
        "SELECT DISTINCT code FROM reporting.d_payment_status"))}
    assert codes == {"pending", "paid", "failed", "cancelled"}, (
        f"betaalstatussen zijn nu {sorted(codes)} — de tegel 'Openstaand saldo' "
        "gaat ervan uit dat 'niet betaald/geannuleerd/mislukt' hetzelfde is als "
        "'In afwachting'; klopt dat niet meer, dan moet die selectie mee")

    losse = {row[0] for row in db_session.execute(text(
        "SELECT DISTINCT status_code FROM reporting.f_payments "
        "WHERE tenant_id = :t"), {"t": TENANT_A})}
    assert losse <= codes, f"betaalrecords met een onbekende status: {losse - codes}"


def test_there_is_one_outstanding_measure_left(db_session, situation):
    """Two answers to one question, both called outstanding, is what went."""
    namen = [o.name for o in BY_KEY.values()
             if o.klass == "Betalingen" and o.is_measure]
    assert namen.count("Openstaand") == 1
    assert "Openstaand volgens status" not in namen
    # And the second answer is still reachable — as a measure plus a filter.
    met_filter = run_validated(
        db_session,
        Selection(object_keys=("payment_amount",),
                  filters=(Filter("payment_status", Operator.EQ,
                                  ("In afwachting",)),)),
        tenant_id=TENANT_A).rows[0]["payment_amount"]
    assert met_filter is not None


def test_forms_are_counted_from_the_forms_and_not_from_the_submissions(
        db_session, situation):
    """The trap of #848, applied to forms.

    A form that nobody filled in must still be counted — "which form is open and
    gets nothing" is exactly a board member's question, and on the submissions
    fact that form silently vanishes.
    """
    from app.domains.forms.api import Form

    leeg = Form(tenant_id=TENANT_A, title="Niemand vulde dit in",
                slug="niemand-vulde-dit-in", share_token="leeg-formulier-token",
                status="open")
    db_session.add(leeg)
    db_session.commit()

    aantal = _total(db_session, "form_count")
    namen = {r["form"] for r in run_validated(
        db_session, Selection(object_keys=("form", "form_count")),
        tenant_id=TENANT_A).rows}
    assert "Niemand vulde dit in" in namen, (
        "een formulier zonder inzendingen hoort in de telling te staan")
    assert aantal >= 1


def test_the_form_measures_say_what_they_count(db_session, situation):
    """One submission with eight filled fields is 1 and 8 — both useful, and
    neither name said so."""
    assert BY_KEY["submission_answers"].name == "Ingevulde velden"
    assert BY_KEY["submission_count"].name == "Aantal inzendingen"


def test_the_leden_class_no_longer_carries_a_state_as_a_measure(db_session,
                                                                situation):
    """Nieuw, Vernieuwd and Vervallen were never three quantities."""
    namen = {o.name for o in BY_KEY.values()
             if o.klass == "Leden" and o.is_measure}
    assert not ({"Nieuw", "Vernieuwd", "Vervallen"} & namen)
    assert "Aantal leden (hoofdlid)" in namen and "Aantal leden (personen)" in namen

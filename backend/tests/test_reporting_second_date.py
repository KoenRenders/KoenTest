"""A fact has more than one date, and now more than one of them rolls up (#895).

Koen asked whether every date field needs all four granularities. It does not —
that is what the shared date dimension is for. What a **second** date needs is one
extra join, not four more columns.

Measured before this issue: `f_payments.paid_date`, `f_tasks.done_date` and the
activity's first and last date were in the views and unreachable as a roll-up. So
*"betalingen per betaalmaand"* could not be asked while the column was right there.

**A role is the same dimension under its own alias.** `d_paid_date` reads from
`reporting.d_date` and hangs off a different column of the fact. No second view, no
second copy of the calendar logic, and the day/month/quarter/year of #894 work on
it unchanged.

**The role is in the name — "Betaaldatum › Maand" and not a second bare "Maand".**
Two dates on one fact means two objects that could both be called Maand; as soon as
the same concept appears twice, the difference belongs on the screen and not in
something you have to remember (#894, #871).

**The ratchet is the point of the gate**, in the shape of #780: every date column
in a fact is reachable as a roll-up date, unless it is on a list that may only
shrink. Two halves make the difference between a ratchet and a graveyard — every
exemption carries its reason on the same line, and an exemption pointing at a
column that no longer exists turns the gate red as well.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.domains.reporting.api import Selection, run_validated
from app.domains.reporting.universe import DIMENSION_BY_KEY, JOINS, OBJECTS
from tests._reporting_seed import TENANT_A, seed


# Elke datumkolom in een feit is bereikbaar als oprolbare datum, TENZIJ ze hier
# staat — met haar reden op dezelfde regel. Deze lijst mag alleen krimpen.
UITZONDERINGEN: dict[str, str] = {
    "f_payments.created_at": "bron van date_key; de sleuteldatum vertegenwoordigt hem al",
    "f_form_submissions.submitted_at": "bron van date_key; idem",
    "f_tasks.created_at": "bron van date_key; idem",
    "f_tasks.done_at": "bron van done_date, dat wél een rol heeft",
    "f_members.created_at": "bron van date_key; idem",
    "f_activities.created_at": "bron van date_key; idem",
    "f_forms.created_at": "bron van date_key; idem",
    "f_registrations.registered_at": "bron van date_key; idem",
    "f_activities.date_key": "is de einddatum, en die heeft haar eigen rol (#901)",
}

# Twee vermeldingen zijn er bij het schrijven al uit gevallen: `f_payments.paid_at`
# en `f_registrations.created_at` bestaan niet — de weergaven noemen die kolommen
# `paid_date` en `registered_at`. De tweede helft van de poort vond ze meteen, wat
# precies het punt is: zonder die helft had ik hier twee regels laten staan die
# grondig lijken en niets dekken.

# Twee feiten kwamen bij het schrijven van deze poort boven water: `f_members` en
# `f_forms` droegen een `date_key` waar niets aan hing, dus hun eigen sleuteldatum
# was niet oprolbaar. Allebei gejoind — dat is precies wat de ratel hoort te doen.


@pytest.fixture
def situation(db_session):
    return seed(db_session)


@pytest.fixture
def betaald_in_andere_maand(db_session, situation):
    """Eén betaling die tachtig dagen ná haar aanmaak betaald is.

    In de test en niet in de gedeelde seed: die seed draagt met de hand uitgerekende
    verwachtingen voor elk bedrag, en er een rij bij zetten verschuift er een stuk
    of tien. Hier hoort ze ook thuis — zij is wat déze vraag meetbaar maakt.
    """
    from app.domains.payment.api import PaymentRecord

    rij = db_session.query(PaymentRecord).filter(
        PaymentRecord.tenant_id == TENANT_A,
        PaymentRecord.paid_at.isnot(None)).order_by(PaymentRecord.id).first()
    assert rij is not None
    rij.paid_at = rij.created_at + timedelta(days=80)
    db_session.commit()
    return rij


def _rows(db, keys):
    return run_validated(db, Selection(object_keys=tuple(keys)),
                         tenant_id=TENANT_A).rows


def test_payments_per_paid_month_differ_from_per_created_month(
        db_session, betaald_in_andere_maand):
    """The gap this issue carries.

    Same fact, same measure, two dates — and the answers have to differ, otherwise
    the second date is decoration.
    """
    aangemaakt = {r["payment_created_month"]: r["payment_amount_paid"]
                  for r in _rows(db_session, ("payment_created_month", "payment_amount_paid"))}
    betaald = {r["paid_date_month"]: r["payment_amount_paid"]
               for r in _rows(db_session, ("paid_date_month",
                                           "payment_amount_paid"))}
    assert betaald and aangemaakt
    assert betaald != aangemaakt, (
        "per betaalmaand hoort een ander antwoord te geven dan per aanmaakmaand; "
        "geeft het hetzelfde, dan meet deze test niets")

    # En het totaal is hetzelfde: het is dezelfde verzameling betalingen, anders
    # verdeeld. Loopt dat uiteen, dan verliest of verdubbelt de join rijen.
    assert sum(v for v in betaald.values() if v) == \
        sum(v for v in aangemaakt.values() if v)


def test_the_paid_date_lands_in_the_month_it_was_paid(db_session,
                                                      betaald_in_andere_maand):
    """Not just "different" — right."""
    rij = betaald_in_andere_maand
    verwacht = rij.paid_at.strftime("%Y-%m")
    maanden = {r["paid_date_month"] for r in
               _rows(db_session, ("paid_date_month", "payment_amount_paid"))}
    assert verwacht in maanden, f"{verwacht} ontbreekt in {sorted(maanden)}"
    assert rij.created_at.strftime("%Y-%m") != verwacht, (
        "de fixture hoort een betaling te zetten die in een ANDERE maand betaald "
        "is; doet ze dat niet, dan toetst de regel hierboven niets")


def test_all_four_granularities_work_on_the_role(db_session,
                                                 betaald_in_andere_maand):
    """Test 2 of the issue: the same roll-up on both roles."""
    for korrel in ("paid_date_year", "paid_date_quarter", "paid_date_month",
                   "paid_date_day"):
        rijen = _rows(db_session, (korrel, "payment_amount_paid"))
        assert rijen, korrel
        assert all(korrel in rij for rij in rijen), korrel


def test_a_task_rolls_up_on_the_day_it_was_closed(db_session, situation):
    """The second real gap: tasks closed per month."""
    rijen = _rows(db_session, ("done_date_month", "task_count"))
    assert isinstance(rijen, list)
    assert all("done_date_month" in rij for rij in rijen)


def test_the_role_is_visible_in_the_name(db_session, situation):
    """Two dates on one fact means two objects that could both be "Maand"."""
    namen = {o.key: o.name for o in OBJECTS}
    assert namen["paid_date_month"] == "Betaaldatum › Maand"
    assert namen["done_date_year"] == "Afhandeldatum › Jaar"
    # En sinds #901 draagt óók de sleuteldatum de naam van haar onderwerp: er is
    # geen kale "Maand" meer die per feit iets anders betekent.
    assert namen["payment_created_month"] == "Aanmaakdatum › Maand"
    assert not any(n == "Maand" for n in namen.values())


def test_a_role_reads_the_shared_calendar_and_not_a_copy():
    """One view, two aliases. A second copy of the calendar would drift."""
    for sleutel in ("d_paid_date", "d_done_date", "d_activity_start",
                    "d_activity_end"):
        assert DIMENSION_BY_KEY[sleutel].source == "d_date"


# ── De ratel ────────────────────────────────────────────────────────────────

def _date_columns(db) -> set[str]:
    """Every date/timestamp column of every fact view, as `fact.column`."""
    return {f"{rij[0]}.{rij[1]}" for rij in db.execute(text(
        "SELECT c.table_name, c.column_name "
        "FROM information_schema.columns c "
        "WHERE c.table_schema = 'reporting' AND c.table_name LIKE 'f\\_%' "
        "  AND c.data_type IN ('date', 'timestamp with time zone', "
        "                      'timestamp without time zone')"))}


def _rolled_up(db) -> set[str]:
    """Every fact column that a date role (or the key date) hangs off."""
    bereikt = set()
    for join in JOINS:
        doel = DIMENSION_BY_KEY.get(join.dimension)
        if doel is None or doel.source != "d_date":
            continue
        for fact_column, _dim_column in join.pairs:
            bereikt.add(f"{join.fact}.{fact_column}")
    return bereikt


def test_every_date_column_rolls_up_or_is_exempt_with_a_reason(db_session,
                                                               situation):
    """The gate, in the shape of #780: a list that may only shrink.

    **It found two on its first run**, which is the argument for writing it:
    `f_members` and `f_forms` carried a `date_key` with nothing joined to it, so
    their own key date did not roll up. Both are joined now.

    **And broken once on purpose.** A view `reporting.f_verzonnen` with a
    `cancelled_at` column, no role and no exemption, made this fail naming
    `f_verzonnen.cancelled_at`; dropping it made it green. A whole extra view and
    not a column bolted onto a real one — a view definition is a SELECT, so
    appending a column to its text produces a syntax error rather than a test.
    """
    kolommen = _date_columns(db_session)
    assert len(kolommen) >= 8, (
        f"maar {len(kolommen)} datumkolommen gevonden — draait deze poort wel "
        "tegen het echte schema?")
    bereikt = _rolled_up(db_session)
    ontbreekt = sorted(kolommen - bereikt - set(UITZONDERINGEN))
    assert not ontbreekt, (
        "datumkolommen zonder oprolling en zonder uitzondering: "
        + ", ".join(ontbreekt)
        + " — geef ze een rol, of zet ze in UITZONDERINGEN mét reden")


def test_the_gate_goes_red_on_a_new_date_column_without_a_role(db_session,
                                                               situation):
    """The counter-proof of the first half, run rather than described."""
    db_session.execute(text(
        "CREATE VIEW reporting.f_verzonnen AS "
        "SELECT 1 AS tenant_id, CURRENT_TIMESTAMP AS cancelled_at"))
    db_session.commit()
    try:
        with pytest.raises(AssertionError, match="cancelled_at"):
            test_every_date_column_rolls_up_or_is_exempt_with_a_reason(
                db_session, situation)
    finally:
        db_session.execute(text("DROP VIEW reporting.f_verzonnen"))
        db_session.commit()
    test_every_date_column_rolls_up_or_is_exempt_with_a_reason(db_session, situation)


def test_an_exemption_for_a_vanished_column_turns_the_gate_red(db_session,
                                                               situation):
    """The second half, and without it the list is a graveyard.

    An exemption that outlives its column keeps a reason on the books for
    something that no longer exists, and a year later the list covers nothing
    while looking thorough.
    """
    kolommen = _date_columns(db_session) | _rolled_up(db_session)
    verdwenen = sorted(set(UITZONDERINGEN) - kolommen)
    assert not verdwenen, (
        "uitzonderingen voor kolommen die niet meer bestaan: "
        + ", ".join(verdwenen) + " — haal ze uit de lijst")

    UITZONDERINGEN["f_payments.verzonnen_at"] = "bestaat niet"
    try:
        with pytest.raises(AssertionError, match="verzonnen_at"):
            test_an_exemption_for_a_vanished_column_turns_the_gate_red(
                db_session, situation)
    finally:
        UITZONDERINGEN.pop("f_payments.verzonnen_at")


def test_every_exemption_carries_a_reason():
    """Zonder reden groeit zo'n lijst en durft niemand er iets uit te halen."""
    kaal = [k for k, reden in UITZONDERINGEN.items() if len(reden.strip()) < 10]
    assert not kaal, f"uitzonderingen zonder reden: {kaal}"


def test_existing_reports_still_group_on_the_key_date(db_session, situation):
    """Test 5: nothing moved for reports that use the key date.

    The #880 gate guards the shipped ones; this is the direct statement that
    adding a second date did not change the first.
    """
    rijen = _rows(db_session, ("payment_created_month", "payment_amount"))
    assert rijen and all("payment_created_month" in rij for rij in rijen)
    totaal = sum(r["payment_amount"] or Decimal("0") for r in rijen)
    alleen = run_validated(db_session,
                           Selection(object_keys=("payment_amount",)),
                           tenant_id=TENANT_A).rows[0]["payment_amount"]
    assert totaal == alleen


def test_a_role_can_be_offered_as_a_filter_without_blowing_up(db_session,
                                                              situation):
    """Every place that puts a view into SQL has to translate the alias first.

    This is the one that was missed. `d_paid_date` is an alias on `d_date`, so the
    name does not exist in the database — and the panel asks for a filter's
    offered values with its **own** query, which built `FROM reporting.d_paid_date`
    and blew up. The main query translated; this one did not.

    Two implementations of one line, and the second missed it. There is one
    `physical_view()` now, called from both. The test drills at the seam rather
    than at the symptom: any future caller that forgets it fails here.
    """
    from app.domains.reporting.api import dimension_values

    for sleutel in ("paid_date_year", "paid_date_month", "done_date_year",
                    "start_date_quarter", "end_date_day"):
        waarden = dimension_values(db_session, sleutel, tenant_id=TENANT_A)
        assert isinstance(waarden, list), sleutel


def test_the_translation_lives_in_one_place():
    """Not a style rule: the copy that drifted is what reached a board member.

    `physical_view()` is the only thing that may turn an object's view into a
    table name. A second copy is how drilling on a payment date became "Er ging
    iets mis".
    """
    import pathlib
    import re

    domein = pathlib.Path(__file__).resolve().parents[1] / "app" / "domains" / "reporting"
    fouten = []
    for pad in domein.glob("*.py"):
        for nummer, regel in enumerate(pad.read_text().splitlines(), start=1):
            if "reporting.{" not in regel or regel.lstrip().startswith("#"):
                continue
            if re.search(r"reporting\.\{(physical_view\(|fact)", regel):
                continue
            fouten.append(f"{pad.name}:{nummer}: {regel.strip()}")
    assert not fouten, (
        "een weergavenaam gaat rechtstreeks de SQL in zonder physical_view():\n"
        + "\n".join(fouten))

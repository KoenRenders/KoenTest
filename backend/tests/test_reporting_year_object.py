"""One object *Jaar*, and the bolt on the invented day (#894).

Koen: *"Ik begrijp dus nog niet waarom we het jaar voor lidmaatschappen dubbel
nodig hebben — dat is hetzelfde veld en de relaties zijn helder."*

The cause was not naming. One shared date dimension carried the year, six facts
joined it, and the two membership facts were the only ones that did not — they had
their own `year` column. Two facts with their own column give two objects, and no
name can fix that.

**Both facts now hang off `d_date` on 1 January of their year**, Koen's decision of
12 September 2026, so there is literally one object *Jaar*.

**The day is invented, so it is bolted shut.** Grouping such a report by month
would drop everything on January: plausible, and meaningless — the same trap as a
detail you could group by (#852). The refusal names the reason, and since #877 it
is drawn as an error rather than as an empty result.

**Broken once, and the break is the interesting part.** The bolt was lifted by
setting `date_grain` back to "day" on `f_memberships`. The report did not fail; it
came back with every membership of all four years under **januari**, one row, a
number that adds up and answers nothing. That is what
`test_the_bolt_goes_red_and_everything_lands_in_january` reproduces — a gate that
only proves an exception was raised would not have shown what it prevents.
"""
from __future__ import annotations

import pytest

from app.domains.reporting.api import Selection, run_validated
from app.domains.reporting.engine import SelectionError
from app.domains.reporting.universe import (
    DATE_GRAINS,
    DATE_OBJECT_GRAIN,
    FACT_BY_KEY,
    OBJECTS,
)
from tests._reporting_seed import EXPECTED, TENANT_A, seed


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _rows(db, keys, **kw):
    return run_validated(db, Selection(object_keys=tuple(keys)),
                         tenant_id=TENANT_A, **kw).rows


def test_there_is_exactly_one_year_object():
    """Koen's complaint, as an assertion."""
    jaren = [o for o in OBJECTS if o.klass == "Tijd" and o.format.value == "year"]
    assert len(jaren) == 1, (
        f"meer dan één jaarobject: {[o.name for o in jaren]}")
    assert jaren[0].key == "date_year" and jaren[0].name == "Jaar"


def test_the_one_year_works_on_a_membership_and_on_a_payment(db_session,
                                                             situation):
    """One object, two facts — which is the whole point of a conformed dimension."""
    leden = _rows(db_session, ("date_year", "membership_households"))
    betalingen = _rows(db_session, ("date_year", "payment_amount"))
    assert leden and betalingen
    assert all("date_year" in rij for rij in leden + betalingen)


def test_the_numbers_are_the_ones_from_before_the_change(db_session, situation):
    """Test 2 of the issue: grouping by year gives what it gave before.

    The seed's expected numbers were worked out by hand for the old
    `membership_year`; they have to survive a move to the shared dimension, or the
    1 January hook is attaching rows to the wrong year.
    """
    y0, y1, y2, y3 = situation["years"]
    rijen = {r["date_year"]: r for r in
             _rows(db_session, ("date_year", "membership_households",
                                "membership_persons"))}
    for offset, jaar in enumerate((y0, y1, y2, y3)):
        assert rijen[jaar]["membership_households"] == \
            EXPECTED["memberships"]["households"][offset], f"gezinnen in {jaar}"
        assert rijen[jaar]["membership_persons"] == \
            EXPECTED["memberships"]["persons"][offset], f"personen in {jaar}"


def test_a_membership_report_refuses_a_month(db_session, situation):
    """The bolt, with the reason in the message."""
    with pytest.raises(SelectionError) as exc:
        _rows(db_session, ("date_month", "membership_households"))
    melding = str(exc.value)
    assert "januari" in melding and "Jaar" in melding


def test_the_bolt_also_covers_a_filter_and_the_person_grain(db_session,
                                                            situation):
    """Two holes a bolt on the select list alone would leave open.

    A date object can enter a selection through a filter without being shown, and
    the second membership fact has the same invented day.
    """
    from app.domains.reporting.engine import Filter, Operator

    with pytest.raises(SelectionError):
        run_validated(db_session,
                      Selection(object_keys=("membership_households",),
                                filters=(Filter("date_day", Operator.EQ,
                                                ("2026-01-01",)),)),
                      tenant_id=TENANT_A)
    with pytest.raises(SelectionError):
        _rows(db_session, ("date_quarter", "membership_person_count"))


def test_the_bolt_goes_red_and_everything_lands_in_january(db_session, situation):
    """The counter-proof, and it shows the damage rather than the message.

    What was broken: `date_grain` on `f_memberships` set back to "day". No error
    followed — the report simply came back with every membership of every year
    under one **januari**, a number that adds up and answers nothing. That is the
    failure the bolt exists to prevent, and why asserting "it raised" would not
    have been enough.
    """
    feit = FACT_BY_KEY["f_memberships"]
    origineel = feit.date_grain
    object.__setattr__(feit, "date_grain", "day")
    try:
        rijen = _rows(db_session, ("date_month", "membership_households"))
        maanden = {r["date_month"] for r in rijen}
        assert maanden, "zonder grendel komt er gewoon een antwoord"
        assert all(m.endswith("-01") for m in maanden), (
            f"alles hoort op januari te vallen: {sorted(maanden)}")
        assert sum(r["membership_households"] for r in rijen) > 0, (
            "en het telt op — precies waarom niemand het zou opmerken")
    finally:
        object.__setattr__(feit, "date_grain", origineel)

    with pytest.raises(SelectionError):
        _rows(db_session, ("date_month", "membership_households"))


def test_every_date_object_declares_its_grain():
    """The gate under the bolt.

    The bolt compares grains, so a date object that is not in the mapping slips
    through every bolt there is — silently, because nothing raises. A new one has
    to be declared here, or this fails.
    """
    datumobjecten = {o.key for o in OBJECTS if o.view == "d_date"}
    assert datumobjecten == set(DATE_OBJECT_GRAIN), (
        f"zonder korrel: {sorted(datumobjecten - set(DATE_OBJECT_GRAIN))}; "
        f"onbekend object: {sorted(set(DATE_OBJECT_GRAIN) - datumobjecten)}")
    assert set(DATE_OBJECT_GRAIN.values()) <= set(DATE_GRAINS)


def test_only_the_membership_facts_are_bolted():
    """A bolt on a fact with a real date would be a bug, not a safeguard."""
    grof = {k: f.date_grain for k, f in FACT_BY_KEY.items()
            if f.date_grain != "day"}
    assert set(grof) == {"f_memberships", "f_membership_persons"}, grof


def test_the_view_comment_records_the_calendar_year_assumption(db_session):
    """Koen's reason, where the next reader will look.

    The 1 January hook is only acceptable because a membership year is a calendar
    year today. Somebody introducing school years has to find that written on the
    view, not guess at it.
    """
    from sqlalchemy import text

    for view in ("f_memberships", "f_membership_persons"):
        commentaar = db_session.execute(text(
            "SELECT obj_description(c.oid, 'pg_class') FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'reporting' AND c.relname = :v"),
            {"v": view}).scalar() or ""
        assert "1 JANUARI" in commentaar.upper(), view
        assert "KALENDERJAAR" in commentaar.upper(), view

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


def test_there_is_exactly_one_bare_year_object():
    """Koen's complaint, as an assertion.

    One *Jaar*, full stop. The roles of #895 are years too — *Betaaldatum › Jaar*
    — but they carry their date in the name and are therefore not what he meant:
    the complaint was two objects that answer the same question without saying
    which is which.
    """
    from app.domains.reporting.universe import DIMENSION_BY_KEY

    uit_de_kalender = {k for k, d in DIMENSION_BY_KEY.items()
                       if d.source == "d_date"}
    jaren = [o for o in OBJECTS
             if o.view in uit_de_kalender and o.format.value == "year"
             and "›" not in o.name]
    assert len(jaren) == 1, (
        f"meer dan één kaal jaarobject: {[o.name for o in jaren]}")
    # Sinds #901 heet het naar zijn onderwerp en staat het bij Leden: één object
    # voor béide lidmaatschapsfeiten, wat de klacht van #894 was.
    assert jaren[0].key == "membership_year"
    assert jaren[0].name == "Lidmaatschapsjaar" and jaren[0].klass == "Leden"


def test_the_one_year_works_on_both_membership_facts(db_session, situation):
    """One object, two facts — which is the whole point of a conformed dimension.

    Not on payments: since #901 a payment has its own dates, because the shared one
    meant something different there. That distinction is exactly what this object
    used to hide.
    """
    gezinnen = _rows(db_session, ("membership_year", "membership_households"))
    personen = _rows(db_session, ("membership_year", "membership_person_count"))
    assert gezinnen and personen
    assert all("membership_year" in rij for rij in gezinnen + personen)


def test_the_numbers_are_the_ones_from_before_the_change(db_session, situation):
    """Test 2 of the issue: grouping by year gives what it gave before.

    The seed's expected numbers were worked out by hand for the old
    `membership_year`; they have to survive a move to the shared dimension, or the
    1 January hook is attaching rows to the wrong year.
    """
    y0, y1, y2, y3 = situation["years"]
    rijen = {r["membership_year"]: r for r in
             _rows(db_session, ("membership_year", "membership_households",
                                "membership_persons"))}
    for offset, jaar in enumerate((y0, y1, y2, y3)):
        assert rijen[jaar]["membership_households"] == \
            EXPECTED["memberships"]["households"][offset], f"gezinnen in {jaar}"
        assert rijen[jaar]["membership_persons"] == \
            EXPECTED["memberships"]["persons"][offset], f"personen in {jaar}"


def test_a_membership_offers_no_level_below_the_year(db_session, situation):
    """Since #901 the bolt has a second lock in front of it, and that is better.

    Every date now belongs to its subject, so the membership facts reach only
    `d_membership_year` — and on that alias the universe declares one object, the
    year. There is simply nothing finer to ask for, which is a stronger guarantee
    than refusing the request: the wrong question cannot be typed.
    """
    from app.domains.reporting.universe import DIMENSION_BY_KEY, joins_for

    for feit in ("f_memberships", "f_membership_persons"):
        kalender = {v for v in joins_for(feit)
                    if DIMENSION_BY_KEY.get(v) is not None
                    and DIMENSION_BY_KEY[v].source == "d_date"}
        assert kalender == {"d_membership_year"}, f"{feit}: {kalender}"

    niveaus = [o.key for o in OBJECTS if o.view == "d_membership_year"]
    assert niveaus == ["membership_year"], niveaus


def test_the_bolt_still_refuses_a_finer_level_if_one_appears(db_session,
                                                             situation):
    """The bolt itself, exercised — because it is now unreachable by design.

    A lock nobody can reach is a lock nobody tests, and then it quietly stops
    working. So a month object is registered on the membership calendar for the
    length of this test, exactly as a future change might: the bolt has to refuse
    it, naming the reason.

    What was broken, in other words: the universe was given the level it does not
    have. Without the bolt that selection would come back with every membership of
    every year under one **januari** — a number that adds up and answers nothing.
    """
    from dataclasses import replace

    from app.domains.reporting.universe import (BY_KEY, DATE_OBJECT_GRAIN,
                                                Format, ObjectKind)

    maand = replace(BY_KEY["membership_year"], key="membership_month_tijdelijk",
                    name="Lidmaatschapsjaar › Maand", sql="{view}.year_month",
                    format=Format.LABEL, kind=ObjectKind.DIMENSION)
    BY_KEY[maand.key] = maand
    DATE_OBJECT_GRAIN[maand.key] = "month"
    try:
        with pytest.raises(SelectionError) as exc:
            _rows(db_session, (maand.key, "membership_households"))
        melding = str(exc.value)
        assert "januari" in melding, melding
        assert "Jaar" in melding, "en wat je dan wél neemt"
    finally:
        BY_KEY.pop(maand.key)
        DATE_OBJECT_GRAIN.pop(maand.key)


def test_the_bolt_also_covers_a_filter(db_session, situation):
    """A date object can enter a selection through a filter without being shown.

    So the check runs over the filters too; a bolt on the select list alone would
    leave that door open.
    """
    from dataclasses import replace

    from app.domains.reporting.engine import Filter, Operator
    from app.domains.reporting.universe import (BY_KEY, DATE_OBJECT_GRAIN,
                                                Format, ObjectKind)

    dag = replace(BY_KEY["membership_year"], key="membership_day_tijdelijk",
                  name="Lidmaatschapsjaar › Datum", sql="{view}.date_key",
                  format=Format.DATE, kind=ObjectKind.DIMENSION)
    BY_KEY[dag.key] = dag
    DATE_OBJECT_GRAIN[dag.key] = "day"
    try:
        with pytest.raises(SelectionError):
            run_validated(db_session,
                          Selection(object_keys=("membership_households",),
                                    filters=(Filter(dag.key, Operator.EQ,
                                                    ("2026-01-01",)),)),
                          tenant_id=TENANT_A)
    finally:
        BY_KEY.pop(dag.key)
        DATE_OBJECT_GRAIN.pop(dag.key)


def test_every_date_object_declares_its_grain():
    """The gate under the bolt.

    The bolt compares grains, so a date object that is not in the mapping slips
    through every bolt there is — silently, because nothing raises. A new one has
    to be declared here, or this fails.
    """
    # Ook de rollen van #895: die lezen dezelfde kalender onder een eigen alias,
    # en een rol zonder korrel zou net zo goed door elke grendel glippen.
    from app.domains.reporting.universe import DIMENSION_BY_KEY

    datumviews = {k for k, d in DIMENSION_BY_KEY.items() if d.source == "d_date"}
    datumviews.add("d_date")
    datumobjecten = {o.key for o in OBJECTS if o.view in datumviews}
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

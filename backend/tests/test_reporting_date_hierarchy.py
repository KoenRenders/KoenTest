"""The date hierarchy: one line instead of four (#899).

After #895 the class *Tijd* carried twenty-one entries — five base objects plus
four date roles times four levels. Sixteen of those twenty-one are the same four
levels repeated four times, and nobody reads that as four times the same thing:
it reads as sixteen choices.

Koen asked whether a crosstab should let you drill from year down to date and back
up. That is two things, and this is the first: **declare the hierarchy**. The
crosstab is unchanged; what changes is the list a person reads.

**A hierarchy is a presentation concept and nothing more.** The levels stay
ordinary objects with their own keys, because that is what saved reports point at
and what every gate inspects. So this step needs no migration: a saved selection
names `paid_date_month`, and that key is untouched.

**And a level stays directly selectable.** *Maand* on the column axis may not
become a detour via *Jaar* — a hierarchy you can only enter from the top takes away
something that works today. That is the second test below, and it is the one that
would fail if this were built as a drill-only tree.
"""
from __future__ import annotations

import pytest

from app.domains.reporting.api import (BY_KEY, Selection, classes_with_objects,
                                       run_validated)
from app.domains.reporting.universe import HIERARCHIES, HIERARCHY_OF, OBJECTS
from tests._reporting_seed import TENANT_A, seed
from tests.test_reporting_panel_ui import login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _datumregels() -> list:
    """Elke hiërarchieregel in het paneel, over alle klassen heen.

    Sinds #901 staat er geen klasse *Tijd* meer: elke datum hoort bij haar
    onderwerp. Het aantal dat #899 terugbracht wordt dus over de klassen geteld en
    niet meer binnen één ervan.
    """
    return [entry for _naam, objecten in classes_with_objects()
            for entry in objecten if hasattr(entry, "level_keys")]


def test_every_date_is_one_line_and_not_four():
    """The count, and it is the test that catches the usual failure.

    This kind of tidy-up fails silently by **adding** a layer rather than
    replacing one: the hierarchy appears and the four lines per date stay. So the
    number is asserted, not the presence of the hierarchy.

    Ten hierarchies of four levels is forty objects on ten lines. Counted over the
    classes since #901, because the class *Tijd* is gone — each date now sits with
    its subject.
    """
    regels = _datumregels()
    niveaus = sum(len(r.level_keys) for r in regels)
    assert len(regels) == 10, (
        f"{len(regels)} datumregels: {[r.name for r in regels]}")
    assert niveaus >= 40, f"{niveaus} niveaus achter {len(regels)} regels"


def test_a_level_is_still_directly_selectable(db_session, situation):
    """The thing that may not be lost.

    Every level keeps its own key, so a report can name *Maand* without naming
    *Jaar* first — in the panel, in a saved selection, and on the column axis.
    """
    rijen = run_validated(
        db_session,
        Selection(object_keys=("paid_date_month", "payment_amount_paid")),
        tenant_id=TENANT_A).rows
    assert rijen and "paid_date_month" in rijen[0]


def test_the_panel_offers_every_level_as_its_own_button(client, db_session,
                                                        situation):
    """One line, four buttons — not one button you have to drill into."""
    login(client, db_session)
    tekst = client.get("/admin/rapporten/paneel").text
    for sleutel in ("paid_date_year", "paid_date_quarter", "paid_date_month",
                    "paid_date_day"):
        assert f'value="{sleutel}"' in tekst, sleutel


def test_the_level_buttons_read_as_levels_and_not_as_repeats(client, db_session,
                                                             situation):
    """The role is on the line; the buttons carry only their level.

    "Betaaldatum" once with *Jaar · Kwartaal · Maand · Datum* beside it, instead of
    four lines each spelling out "Betaaldatum › …". That repetition is exactly what
    made twenty-one entries feel like twenty-one choices.
    """
    login(client, db_session)
    tekst = client.get("/admin/rapporten/paneel").text
    assert tekst.count("Betaaldatum › ") == 0, (
        "de rol staat één keer op de regel, niet vier keer op de knoppen")
    assert "Betaaldatum" in tekst


def test_every_level_key_still_exists_as_an_object():
    """A hierarchy that swallowed its levels would break every saved report.

    Selections store keys. Turning the levels into something that only lives
    inside the hierarchy would silently orphan `paid_date_month` — which is what
    the gate of #880 would catch, but only after the fact.
    """
    for hier in HIERARCHIES:
        for sleutel in hier.level_keys:
            assert sleutel in BY_KEY, f"{hier.key}: {sleutel} bestaat niet"
        assert len(hier.level_keys) >= 4


def test_no_time_object_is_left_outside_a_hierarchy():
    """Otherwise the list grows back one object at a time."""
    from app.domains.reporting.universe import DIMENSION_BY_KEY

    # Alleen wat uit de KALENDER komt. Een `member_since` of een `activity_year`
    # is een jaartal uit het feit zelf en heeft geen niveaus eronder; die in een
    # hiërarchie duwen zou vier lege beloftes maken.
    uit_de_kalender = {k for k, d in DIMENSION_BY_KEY.items()
                       if d.source == "d_date"}
    los = [o.key for o in OBJECTS
           if o.view in uit_de_kalender and o.key not in HIERARCHY_OF
           and o.key != "membership_year"]
    assert not los, (
        f"kalenderobjecten zonder hiërarchie: {los} — zet ze in een hiërarchie, "
        "of de lijst groeit terug naar losse niveaus")


def test_the_full_month_label_is_gone():
    """"Maand voluit" was a leftover from before the roles (#901).

    It existed only on the shared date and on none of the four roles, and since
    #852 it cannot be grouped on. `2026-03` sorts chronologically by itself and
    reads just as well — the alternative was making three more copies of it, and
    that is not a choice.
    """
    assert "date_month_label" not in BY_KEY
    assert not any("voluit" in o.name.lower() for o in OBJECTS)


def test_the_roles_of_895_still_roll_up_on_every_level(db_session, situation):
    """The ratchet of #895 may not be undone by a hierarchy.

    Grouping a date column into a tidier list must not make any of it
    unreachable — that would trade a real capability for a shorter screen.
    """
    for sleutel, klasse in (("done_date_year", "Taken"),
                            ("start_date_month", "Activiteiten"),
                            ("end_date_quarter", "Activiteiten"),
                            ("paid_date_day", "Betalingen")):
        obj = BY_KEY[sleutel]
        assert obj.klass == klasse, f"{sleutel} staat in {obj.klass}"
        assert sleutel in HIERARCHY_OF, sleutel

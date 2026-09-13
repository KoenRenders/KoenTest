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


def _tijd_entries():
    return next(objecten for naam, objecten in classes_with_objects()
                if naam == "Tijd")


def test_the_time_class_is_five_lines_instead_of_twenty_one():
    """The count, and it is the test that catches the usual failure.

    This kind of tidy-up fails silently by **adding** a layer rather than
    replacing one: the hierarchy appears and the sixteen lines stay. So the number
    is asserted, not the presence of the hierarchy.
    """
    entries = _tijd_entries()
    assert len(entries) == 5, (
        f"Tijd toont {len(entries)} regels: "
        f"{[getattr(e, 'name', e) for e in entries]}")
    assert all(hasattr(e, "level_keys") for e in entries), (
        "alle vijf horen hiërarchieën te zijn")


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
    los = [o.key for o in OBJECTS
           if o.klass == "Tijd" and o.key not in HIERARCHY_OF]
    assert not los, (
        f"objecten in Tijd zonder hiërarchie: {los} — zet ze in een hiërarchie, "
        "of de klasse groeit terug naar een lijst van losse niveaus")


def test_the_shared_date_keeps_its_full_month_level():
    """"Maand voluit" is a detail, not a fifth role — it belongs to the date."""
    datum = next(h for h in HIERARCHIES if h.key == "date")
    assert "date_month_label" in datum.level_keys
    assert BY_KEY["date_month_label"].kind.value == "detail"


def test_the_roles_of_895_still_roll_up_on_every_level(db_session, situation):
    """The ratchet of #895 may not be undone by a hierarchy.

    Grouping a date column into a tidier list must not make any of it
    unreachable — that would trade a real capability for a shorter screen.
    """
    for sleutel in ("done_date_year", "start_date_month", "end_date_quarter"):
        obj = BY_KEY[sleutel]
        assert obj.klass == "Tijd" and sleutel in HIERARCHY_OF, sleutel

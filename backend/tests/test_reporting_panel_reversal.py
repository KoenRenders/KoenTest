"""Undoing a choice where you made it (#876, #872).

The panel was built add-only, and it showed up three times: a column axis you
could not clear (#873), an object you could not click off (#876), a class you
could not fold shut (#872).

**One decision about how reversal works, made once.** It follows the kind of
control and not the screen:

- The column axis is **one out of N** — a radio. No user interface anywhere turns
  a radio off by clicking it again, so it gets an explicit *"geen"* (#873).
- An object in the selection is **in or out** — a checkbox. There a second click
  is the standard idiom, and an extra "remove" control beside a list of 93 lines
  would be noise.

Both carry `aria-pressed`, so the state is announced the same way whichever of the
two you meet.

**What #872 stands or falls on is that the fold survives an interaction.** The
panel swaps its own `outerHTML` on every click, so Alpine state is gone the moment
you pick an object — fold three classes, choose one thing, and you face all 93
lines again. So the fold travels in the panel state, and `test_the_fold_survives_
choosing_an_object` is the test that says so.
"""
from __future__ import annotations

import re

import pytest

from tests._reporting_seed import seed
from tests.test_reporting_panel_ui import login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def _paneel(client, query: str = ""):
    antwoord = client.get(f"/admin/rapporten/paneel{query}")
    assert antwoord.status_code == 200
    return antwoord.text


def _objectknop(tekst: str, key: str) -> str:
    """The button for one object in the OBJECTS list, and nothing else.

    Two other buttons carry the same key: the chosen-columns strip has its own
    remove button, and the crosstab's column chooser has one with `aria-pressed`
    as well. Matching loosely would pass on the wrong element — and this whole
    file is about which button does what. So: `add` or `remove`, and pressed.
    """
    knoppen = [m.group(0) for m in re.finditer(r"<button\b[^>]*>", tekst)
               if f'value="{key}"' in m.group(0) and "aria-pressed" in m.group(0)
               and ('name="add"' in m.group(0) or 'name="remove"' in m.group(0))]
    assert len(knoppen) == 1, (
        f"verwacht één objectknop voor {key}, gevonden {len(knoppen)}")
    return knoppen[0]


# ── #876: een object uit de selectie klikken ────────────────────────────────

def test_a_chosen_object_offers_remove_instead_of_add(client, db_session,
                                                      situation):
    """The whole bug: the button always sent `add`, even beside a ✓."""
    login(client, db_session)
    knop = _objectknop(_paneel(client, "?object=payment_amount"), "payment_amount")
    assert 'name="remove"' in knop
    assert 'name="add"' not in knop


def test_an_unchosen_object_still_offers_add(client, db_session, situation):
    login(client, db_session)
    knop = _objectknop(_paneel(client), "payment_amount")
    assert 'name="add"' in knop
    assert 'name="remove"' not in knop


def test_clicking_a_chosen_object_takes_it_out(client, db_session, situation):
    login(client, db_session)
    tekst = _paneel(client, "?object=payment_amount&object=payment_method"
                            "&remove=payment_amount")
    assert 'name="object" value="payment_amount"' not in tekst
    assert 'name="object" value="payment_method"' in tekst


def test_the_state_is_announced_and_the_title_says_what_the_click_does(
        client, db_session, situation):
    """The ✓ alone reads as "done", not as "click to undo"."""
    login(client, db_session)
    knop = _objectknop(_paneel(client, "?object=payment_amount"), "payment_amount")
    assert 'aria-pressed="true"' in knop
    assert "uit het rapport te halen" in knop


def test_removing_an_object_leaves_its_filter_alone(client, db_session,
                                                    situation):
    """Two separate actions with two separate remove buttons.

    A click that silently drops a filter as well changes the result in a way
    nobody expects — and the filter has its own control right beside it.
    """
    login(client, db_session)
    tekst = _paneel(client, "?object=payment_method&object=payment_amount"
                            "&filter=payment_method&op_payment_method=eq"
                            "&v_payment_method=Online&remove=payment_method")
    assert 'name="object" value="payment_method"' not in tekst
    assert 'name="filter" value="payment_method"' in tekst, (
        "de filter hoort te blijven staan; hij is een eigen keuze met een eigen "
        "verwijderknop")


# ── #872: klassen in- en uitklappen ─────────────────────────────────────────

def test_every_class_starts_open(client, db_session, situation):
    """Koen asked for default-open: the screen looks the way it does today."""
    login(client, db_session)
    tekst = _paneel(client)
    assert 'aria-expanded="false"' not in tekst
    assert tekst.count('aria-expanded="true"') >= 6, "zes klassen, alle open"


def test_a_class_can_be_folded_shut(client, db_session, situation):
    login(client, db_session)
    tekst = _paneel(client, "?toggle_class=Leden")
    assert 'name="closed" value="Leden"' in tekst
    assert 'aria-expanded="false"' in tekst


def test_the_fold_survives_choosing_an_object(client, db_session, situation):
    """What this issue stands or falls on.

    Default-open plus no memory is a worthless feature: you fold three classes,
    pick one object, and face all 93 lines again. The panel replaces its own
    outerHTML, so the fold cannot live in the browser — it travels in the state.
    """
    login(client, db_session)
    tekst = _paneel(client, "?closed=Leden&closed=Taken&add=payment_amount")
    assert 'name="closed" value="Leden"' in tekst
    assert 'name="closed" value="Taken"' in tekst
    assert 'name="object" value="payment_amount"' in tekst, (
        "en het gekozen object staat erin, anders meet deze test niets")


def test_a_folded_class_shows_how_many_you_chose_in_it(client, db_session,
                                                       situation):
    """With the selection summary dropped at Koen's request, this is the only
    place a closed class still shows your choice."""
    login(client, db_session)
    tekst = _paneel(client, "?object=payment_amount&object=payment_method"
                            "&closed=Betalingen")
    # Two objects chosen, both in Betalingen, and that class is shut.
    assert ">2</span>" in tekst, (
        "een dichte klasse hoort te tonen hoeveel je erin koos; zonder dat "
        "verbergt inklappen precies wat je wou overzien")


def test_folding_a_class_does_not_change_the_selection(client, db_session,
                                                       situation):
    """Folding is a viewing preference. It may not touch the report."""
    login(client, db_session)
    query = "?object=payment_method&object=payment_amount"
    voor = _paneel(client, query)
    na = _paneel(client, query + "&toggle_class=Leden")
    for sleutel in ("payment_method", "payment_amount"):
        assert f'name="object" value="{sleutel}"' in voor
        assert f'name="object" value="{sleutel}"' in na


def test_toggling_twice_opens_it_again(client, db_session, situation):
    login(client, db_session)
    tekst = _paneel(client, "?closed=Leden&toggle_class=Leden")
    assert 'name="closed" value="Leden"' not in tekst


def test_an_unknown_class_is_ignored(client, db_session, situation):
    """State arrives in a query string, so it is user input."""
    login(client, db_session)
    tekst = _paneel(client, "?closed=Verzonnen&toggle_class=Ookverzonnen")
    assert 'name="closed" value="Verzonnen"' not in tekst
    assert 'name="closed" value="Ookverzonnen"' not in tekst


# ── De beslissing zelf ──────────────────────────────────────────────────────

def test_the_two_reversal_idioms_stay_apart(client, db_session, situation):
    """One decision, applied by kind of control and not by screen.

    The column axis keeps its explicit "geen" and the object keeps its second
    click. If a later change makes the axis a second-click toggle as well, the
    "geen" button disappears and this test says so — the point is that both are
    deliberate, not that one of them is.
    """
    login(client, db_session)
    tekst = _paneel(client, "?object=payment_method&object=payment_payable_type"
                            "&object=payment_amount&layout=pivot")
    assert 'name="set_column" value=""' in tekst, "de as: een expliciete 'geen'"
    assert 'name="remove"' in _objectknop(tekst, "payment_method"), (
        "het object: een tweede klik")

"""A pivot without a column axis, choosable from the screen (#873).

Koen, looking at v2.3.0 on HDEV: *"Ik wil een draaitabel met 'groepen' als rijen en
dan de measures totaliserend op die groepen."* The engine could already do it —
`build_pivot` stopped refusing a column-less selection in #850, where a subtotal
per board member needed exactly this shape. The panel had no way to say it: the
button row set an axis and nothing set it back to none.

**Why an empty `pivot_column` was not enough by itself.** It means two different
things — "there is none yet", where picking one for the user is helpful, and "the
user just cleared it", where picking one undoes what he asked. The first is the
existing behaviour that one click on *Draaitabel* produces a crosstab rather than
a question, and that stays. So the choice travels as its own flag, `no_column`,
and the fallback only fires when it is absent.

**The test that matters is the third one.** The column axis may change the shape
and must not change the count: the grand total is the same with it and without it.
Diverge, and the axis is not a form but a filter.
"""
from __future__ import annotations

import pytest

from app.domains.reporting.api import Selection, build_pivot
from tests._reporting_seed import TENANT_A, seed
from tests.test_reporting_panel_ui import login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


BASIS = ("object=payment_method&object=payment_payable_type&object=payment_amount")


def test_the_panel_offers_a_way_to_clear_the_column_axis(client, db_session,
                                                         situation):
    login(client, db_session)
    fragment = client.get(f"/admin/rapporten/paneel?{BASIS}&set_layout=pivot")
    assert 'name="set_column" value=""' in fragment.text, (
        "er hoort een knop te staan die de kolomas leegmaakt")


def test_clearing_it_sticks_instead_of_being_refilled(client, db_session,
                                                      situation):
    """The bug underneath the report: the axis came straight back.

    One request clears it, the next carries the state — and without the flag the
    fallback would pick the last dimension again, so the button would look broken
    rather than absent.
    """
    login(client, db_session)
    leeg = client.get(f"/admin/rapporten/paneel?{BASIS}&layout=pivot&set_column=")
    assert 'name="pivot_column" value=""' in leeg.text
    assert 'name="no_column" value="1"' in leeg.text

    # The next request, as the browser sends it: the state, no command.
    volgend = client.get(
        f"/admin/rapporten/paneel?{BASIS}&layout=pivot&pivot_column=&no_column=1")
    assert 'name="pivot_column" value=""' in volgend.text, (
        "de kolomas hoort leeg te blijven; komt hij terug, dan doet 'geen' niets")


def test_the_grand_total_is_the_same_with_and_without_a_column_axis(db_session,
                                                                    situation):
    """The test this issue rests on.

    The axis rearranges cells; it may not change what is counted. If these two
    differ, one of the two shapes is counting something else and the axis is not a
    form but a filter.
    """
    objecten = ("payment_method", "payment_payable_type", "payment_amount")
    met = build_pivot(db_session,
                      Selection(object_keys=objecten, layout="pivot",
                                pivot_column="payment_payable_type"),
                      tenant_id=TENANT_A)
    zonder = build_pivot(db_session,
                         Selection(object_keys=objecten, layout="pivot"),
                         tenant_id=TENANT_A)
    assert met.grand_total == zonder.grand_total, (
        f"eindtotaal met kolomas {met.grand_total}, zonder {zonder.grand_total}")
    assert met.grand_total, "er valt iets te tellen, anders meet deze test niets"


def test_without_an_axis_the_rows_carry_subtotals_and_no_columns(db_session,
                                                                 situation):
    """The shape Koen asked for: groups as rows, measures as columns."""
    pivot = build_pivot(
        db_session,
        Selection(object_keys=("payment_method", "payment_payable_type",
                               "payment_amount"), layout="pivot"),
        tenant_id=TENANT_A)
    assert pivot.column_column is None and not pivot.column_values
    assert any(rij.is_subtotal for rij in pivot.rows), (
        "het subtotaal per eerste rijdimensie is het enige verschil met de "
        "tabelvorm — is het er niet, dan is deze vorm zinloos")


def test_one_click_on_the_crosstab_still_picks_an_axis(client, db_session,
                                                       situation):
    """Unchanged behaviour, and deliberately so.

    #873 asks for a way to clear the axis, not for a different default. Removing
    the fallback as a side effect would have been a second change hiding inside
    the first.
    """
    login(client, db_session)
    fragment = client.get(f"/admin/rapporten/paneel?{BASIS}&set_layout=pivot")
    assert 'name="pivot_column" value="payment_payable_type"' in fragment.text


def test_the_screen_says_what_the_two_shapes_differ_in(client, db_session,
                                                       situation):
    """Two shapes that look alike, with the difference written nowhere, is how
    this question gets asked again."""
    login(client, db_session)
    fragment = client.get(
        f"/admin/rapporten/paneel?{BASIS}&layout=pivot&pivot_column=&no_column=1")
    assert "subtotaal per groep" in fragment.text


def test_a_stacked_chart_keeps_its_axis(client, db_session, situation):
    """A stacked chart without a column axis is not a shape, it is a bar chart.

    So the clearing button is not offered there, and the flag does not survive a
    switch to it — otherwise a user who cleared the axis on a pivot would land on
    an empty chart.
    """
    login(client, db_session)
    fragment = client.get(
        f"/admin/rapporten/paneel?{BASIS}&pivot_column=&no_column=1"
        "&set_layout=stacked")
    assert 'name="pivot_column" value="payment_payable_type"' in fragment.text
    assert 'name="no_column" value=""' in fragment.text


def test_a_saved_pivot_without_an_axis_opens_the_way_it_was_saved(db_session,
                                                                  situation):
    """The report of #850 is exactly this shape, and reopening it must not refill
    the axis — that would silently rewrite somebody's saved report."""
    from app.domains.reporting.api import (list_saved_reports,
                                           selection_from_dict)

    rapport = next(r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                                 viewer="")
                   if r.builtin_key == "members_per_board_member")
    selectie = selection_from_dict(rapport.selection)
    assert selectie.layout == "pivot" and not selectie.pivot_column

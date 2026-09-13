"""Drilling and rolling up in the crosstab (#899, stap 2).

Koen: *"Moet je in een draaitabel niet kunnen drillen en oprollen van jaar naar
datum en terug omhoog?"*

**Drilling replaces the level; it does not unfold rows.** Click 2026 and the report
stands on quarter, filtered on 2026 — which is what a classic drill does, and what
keeps the crosstab one selection with one query plan. Rows that each hold their own
open/closed state would be a tree: a query per node, and subtotals across mixed
levels. That is a different machine, not an extension of this one, and it would
have to earn its cost separately.

The consequence of that choice is testable, and it is the point of the second test
here: **the grand total does not move when you drill.** Replacing a level narrows
what you see, not what is counted — the filter that comes with the drill is
visible in the filter list, so nothing is hidden.

**And the way back has to exist.** Without it a drill is a one-way street: you click
2026, land on quarters, and have to rebuild the report to get back. Rolling up also
takes the filter with it — that filter was the staircase down, not a choice the
user made, and leaving it behind would silently keep the report on 2026.
"""
from __future__ import annotations

import pytest

from app.domains.reporting.api import HIERARCHY_OF, Selection, build_pivot
from tests._reporting_seed import TENANT_A, seed
from tests.test_reporting_panel_ui import login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


BASIS = ("object=payment_created_year&object=payment_amount&layout=pivot"
         "&pivot_column=&no_column=1")


def _paneel(client, query: str):
    antwoord = client.get(f"/admin/rapporten/paneel?{query}")
    assert antwoord.status_code == 200
    return antwoord.text


def test_a_year_label_is_clickable_in_the_crosstab(db_session, situation):
    """The crosstab says which column can go deeper; the kit macro renders it."""
    kruis = build_pivot(
        db_session,
        Selection(object_keys=("payment_created_year", "payment_amount"), layout="pivot"),
        tenant_id=TENANT_A)
    assert kruis.row_drill == ["payment_created_quarter"], kruis.row_drill


def test_the_drill_button_carries_the_url_it_posts_to(client, db_session,
                                                      situation):
    """The thing that was missing, and the reason it went unnoticed.

    The button rendered with the right name and the right value, and the tests in
    this file — markup and route — were both green. But it had no `hx-get`, and
    `type="button"` submits nothing: clicking did literally nothing. The kit macro
    knew what to send back and not where to send it, and nobody had given it the
    URL.

    This assertion is cheap and catches the regression, but it is **not enough**:
    it reads the same markup the blind spot lived in. `tests_e2e/
    test_drillen_in_de_draaitabel.py` clicks the button in a real browser, and
    that is the layer that proves it does something.
    """
    login(client, db_session)
    tekst = _paneel(client, BASIS)
    knoppen = [m for m in tekst.split("<button") if 'name="drill"' in m]
    assert knoppen, "er hoort een drill-knop te staan"
    for knop in knoppen:
        assert "hx-get=" in knop.split(">")[0], (
            "een drill-knop zonder hx-get doet niets — de markup is dan decor")


def test_the_deepest_level_offers_no_further_drill(db_session, situation):
    """A dead end has to look like a dead end."""
    kruis = build_pivot(
        db_session,
        Selection(object_keys=("payment_created_day", "payment_amount"), layout="pivot"),
        tenant_id=TENANT_A)
    assert kruis.row_drill == [""]


def test_drilling_replaces_the_level_and_adds_a_visible_filter(client,
                                                               db_session,
                                                               situation):
    login(client, db_session)
    tekst = _paneel(client, f"{BASIS}&drill=payment_created_quarter|2026")
    assert 'name="object" value="payment_created_quarter"' in tekst
    assert 'name="object" value="payment_created_year"' not in tekst
    assert 'name="filter" value="payment_created_year"' in tekst, (
        "de filter die het drillen zette, hoort zichtbaar in de filterlijst te "
        "staan — anders is het rapport stilletjes versmald")


def test_the_grand_total_does_not_move_when_you_drill(db_session, situation):
    """The consequence of replacing instead of unfolding, as an assertion.

    Drilling narrows what you SEE within the group you clicked; it may not change
    what is counted inside that group. So the year's own total has to equal the
    sum of its quarters.
    """
    from app.domains.reporting.engine import Filter, Operator

    jaren = build_pivot(
        db_session,
        Selection(object_keys=("payment_created_year", "payment_amount"), layout="pivot"),
        tenant_id=TENANT_A)
    jaar = jaren.rows[0].labels[0]
    heel_jaar = jaren.rows[0].total["payment_amount"]

    kwartalen = build_pivot(
        db_session,
        Selection(object_keys=("payment_created_quarter", "payment_amount"), layout="pivot",
                  filters=(Filter("payment_created_year", Operator.EQ, (jaar,)),)),
        tenant_id=TENANT_A)
    assert kwartalen.grand_total["payment_amount"] == heel_jaar, (
        f"{jaar} telt {heel_jaar}, zijn kwartalen samen "
        f"{kwartalen.grand_total['payment_amount']}")


def test_rolling_up_takes_the_filter_with_it(client, db_session, situation):
    """The filter was the staircase down, not a choice."""
    login(client, db_session)
    tekst = _paneel(client, "object=payment_created_quarter&object=payment_amount"
                            "&filter=payment_created_year&op_date_year=eq&v_date_year=2026"
                            "&layout=pivot&rollup=payment_created_quarter")
    assert 'name="object" value="payment_created_year"' in tekst
    assert 'name="object" value="payment_created_quarter"' not in tekst
    assert 'name="filter" value="payment_created_year"' not in tekst, (
        "blijft de filter staan, dan staat het rapport stilletjes nog op 2026")


def test_the_way_back_up_is_offered(client, db_session, situation):
    login(client, db_session)
    tekst = _paneel(client, "object=payment_created_quarter&object=payment_amount&layout=pivot")
    assert 'name="rollup" value="payment_created_quarter"' in tekst
    assert "Terug omhoog" in tekst


def test_the_top_level_offers_no_way_up(client, db_session, situation):
    """Otherwise there is a button that does nothing."""
    login(client, db_session)
    tekst = _paneel(client, BASIS)
    assert 'name="rollup" value="payment_created_year"' not in tekst


def test_drilling_carries_the_sort_and_the_column_axis(client, db_session,
                                                       situation):
    """A level that is replaced may not leave a dangling reference behind.

    Sorting on an object that is no longer in the report is refused by the engine,
    so a drill that forgot the sort would produce an error instead of a report.
    """
    login(client, db_session)
    tekst = _paneel(client, "object=payment_created_year&object=payment_method"
                            "&object=payment_amount&sort=payment_created_year&dir=asc"
                            "&layout=pivot&pivot_column=payment_created_year"
                            "&drill=payment_created_quarter|2026")
    assert 'name="sort" value="payment_created_quarter"' in tekst
    assert 'name="pivot_column" value="payment_created_quarter"' in tekst


def test_a_detail_level_is_skipped_when_drilling():
    """"Maand voluit" sits between month and day and cannot be grouped on (#852).

    Drilling into a dead end would be worse than no drill at all, so the step
    skips detail levels.
    """
    datum = HIERARCHY_OF["payment_created_month"]
    assert datum.step("payment_created_month", +1) == "payment_created_day"
    assert datum.step("payment_created_day", -1) == "payment_created_month"


def test_drilling_works_on_a_role_date_too(client, db_session, situation):
    """The roles of #895 are where an alias bug hides.

    `d_paid_date` is an alias on `d_date`, so a place that forgets to translate
    breaks only here — on the shared date the alias and the key are the same
    string. The first version of the browser test drilled on `payment_created_year` and
    stayed green while clicking a payment date gave an error banner.
    """
    login(client, db_session)
    tekst = _paneel(client, "object=paid_date_year&object=payment_amount"
                            "&layout=pivot&pivot_column=&no_column=1"
                            "&drill=paid_date_quarter|2026")
    assert 'name="object" value="paid_date_quarter"' in tekst
    assert 'name="filter" value="paid_date_year"' in tekst


def test_drilling_an_unrelated_value_does_nothing(client, db_session, situation):
    """State arrives in a query string, so it is user input."""
    login(client, db_session)
    tekst = _paneel(client, f"{BASIS}&drill=bestaatniet|2026")
    assert 'name="object" value="payment_created_year"' in tekst
    assert 'name="object" value="bestaatniet"' not in tekst


def test_an_unknown_label_is_not_drillable(db_session, situation):
    """"Onbekend" is the label for an EMPTY value, and there is nothing below it.

    Found by the browser test, and it is the kind of fault a markup test cannot
    see: the button rendered, the click fired, and the server got a filter asking
    for the year "Onbekend". A year column is an integer, so Postgres refused the
    comparison, htmx got a 500 and swapped nothing — a click that did nothing, for
    the second time and for a completely different reason.

    A payment that has not been paid has no payment date, so this is not an edge
    case: it is the normal state of half the payments.
    """
    from sqlalchemy import text

    # Geen enkele betaling betaald: elke betaaldatum is dan leeg.
    db_session.execute(text(
        "UPDATE payment.payment_records SET paid_at = NULL WHERE tenant_id = :t"),
        {"t": TENANT_A})
    db_session.commit()

    kruis = build_pivot(
        db_session,
        Selection(object_keys=("paid_date_year", "payment_amount"),
                  layout="pivot"),
        tenant_id=TENANT_A)
    assert kruis.rows, "er zijn betalingen, dus er is een rij"
    for rij in kruis.rows:
        if rij.labels and rij.labels[0] == "Onbekend":
            assert rij.drillable == [False], (
                "op 'Onbekend' hoort niet doorgeklikt te kunnen worden")
            break
    else:
        pytest.fail("geen 'Onbekend'-rij, dus deze test meet niets")


def test_a_real_value_stays_drillable(db_session, situation):
    """De andere kant, zodat de reparatie niet 'niets is meer doorklikbaar' wordt."""
    kruis = build_pivot(
        db_session,
        Selection(object_keys=("payment_created_year", "payment_amount"), layout="pivot"),
        tenant_id=TENANT_A)
    assert any(rij.drillable == [True] for rij in kruis.rows), (
        "een echt jaartal hoort doorklikbaar te blijven")

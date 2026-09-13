"""Drilling and rolling up in the crosstab (#899, stap 2).

Koen: *"Moet je in een draaitabel niet kunnen drillen en oprollen van jaar naar
datum en terug omhoog?"*

**Drilling ADDS the next level as a row column (#907).** Click 2026 and you get
year and quarter side by side — for *all* years — with the subtotals per year in
between. Koen's objection to the first version was exact: *"Ik vind niet dat op 2026
klikken, 2026 instellen als filter is. In mijn beleving komt er bij drillen een
kolom bij."*

That needs no new machinery: the crosstab already carries several row dimensions
with a subtotal per group — it is what *Leden per bestuurslid* does. Drilling is one
object more in the selection.

**And the click offers a filter without applying one.** The filter row for the date
you clicked appears, empty. The click narrows nothing; it shows *that* you can
narrow and where. That is the whole difference between "clicking filters" and
"clicking offers", and it is what the first version got wrong.

The consequence is testable, and it is the point of the second test here: **the
grand total does not move when you drill.** Adding a level splits rows; it adds and
subtracts nothing.
"""
from __future__ import annotations

import re

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


def test_drilling_adds_a_column_and_keeps_the_one_above(client, db_session,
                                                       situation):
    """Koen's objection, as an assertion: er komt een kolom bij."""
    login(client, db_session)
    tekst = _paneel(client, f"{BASIS}&drill=payment_created_quarter|2026")
    assert 'name="object" value="payment_created_year"' in tekst, (
        "het jaar blijft staan; drillen vervangt niet")
    assert 'name="object" value="payment_created_quarter"' in tekst


def test_the_new_level_comes_right_after_its_parent(client, db_session,
                                                    situation):
    """Kolomvolgorde is rijgroepering: jaar, dan kwartaal, dan de rest.

    Achteraan aanschuiven zou de subtotalen op de verkeerde as zetten en een
    tabel opleveren die klopt en niets zegt.
    """
    login(client, db_session)
    tekst = _paneel(client, "object=payment_created_year&object=payment_method"
                            "&object=payment_amount&layout=pivot&pivot_column="
                            "&no_column=1&drill=payment_created_quarter|2026")
    volgorde = re.findall(r'name="object" value="([^"]+)"', tekst)
    assert volgorde == ["payment_created_year", "payment_created_quarter",
                        "payment_method", "payment_amount"], volgorde


def test_the_click_offers_a_filter_and_filters_nothing(client, db_session,
                                                       situation):
    """De tweede helft, en allebei de kanten worden getoetst.

    Alleen "het filter staat er" zou slagen terwijl het rapport stilzwijgend
    versmald is; alleen "er is niets weggefilterd" zou slagen terwijl het aanbod
    ontbreekt. Het aanbod toetst de markup, het niet-filteren toetst het
    RESULTAAT — een filter dat wel degelijk knipt, zie je aan de rijen en niet aan
    een attribuut.
    """
    login(client, db_session)
    met = _paneel(client, f"{BASIS}&drill=payment_created_quarter|2026")
    assert 'name="filter" value="payment_created_year"' in met, (
        "het filter voor de aangeklikte datum hoort te verschijnen")

    # En dat het niets filtert, op de naad waar de staat een selectie wordt: een
    # filter zonder waarde hoort de query niet te bereiken. De motor weigert een
    # filter zónder waarden, dus als dit lek was, kreeg Koen een foutmelding in
    # plaats van een rapport — wat precies het omgekeerde is van "een klik minder".
    from starlette.datastructures import QueryParams

    from app.domains.reporting.admin_ui import _read_state, _selection

    # De hele querystring en niet een dict: `object` komt meermaals voor, en een
    # dict houdt er één van over — dan vindt het drillen zijn ouder niet.
    staat = _read_state(QueryParams(f"{BASIS}&drill=payment_created_quarter|2026"))
    assert "payment_created_year" in staat["filters"], (
        "het filter hoort in de staat te staan")
    assert not staat["values"].get("payment_created_year"), "en zonder waarde"

    selectie = _selection(staat)
    assert selectie.filters == (), (
        "een leeg filter hoort de query niet te bereiken")
    assert "payment_created_quarter" in selectie.object_keys


def test_the_grand_total_does_not_move_when_you_drill(db_session, situation):
    """De test die dit issue draagt.

    Een niveau toevoegen splitst rijen op en telt niets bij of af. Wijkt het
    eindtotaal af, dan doet drillen iets anders dan het belooft.
    """
    from app.domains.reporting.api import Selection, build_pivot

    jaar = build_pivot(
        db_session,
        Selection(object_keys=("payment_created_year", "payment_amount"),
                  layout="pivot"),
        tenant_id=TENANT_A)
    jaar_kwartaal = build_pivot(
        db_session,
        Selection(object_keys=("payment_created_year", "payment_created_quarter",
                               "payment_amount"), layout="pivot"),
        tenant_id=TENANT_A)

    assert jaar.grand_total == jaar_kwartaal.grand_total, (
        f"eindtotaal per jaar {jaar.grand_total}, met kwartaal erbij "
        f"{jaar_kwartaal.grand_total}")
    assert jaar.grand_total, "er valt iets te tellen"
    assert any(r.is_subtotal for r in jaar_kwartaal.rows), (
        "met twee rijdimensies horen er subtotalen per jaar te staan")


def test_the_way_back_up_is_offered(client, db_session, situation):
    login(client, db_session)
    tekst = _paneel(client, "object=payment_created_year"
                            "&object=payment_created_quarter&object=payment_amount"
                            "&layout=pivot")
    assert 'name="rollup" value="payment_created_quarter"' in tekst
    assert "Terug omhoog" in tekst


def test_a_single_level_offers_no_way_up(client, db_session, situation):
    """Anders staat er een knop die het rapport in iets anders verandert.

    Oprollen betekent "één niveau minder". Is er maar één datumkolom, dan zou die
    knop de enige datum weghalen, en dat is geen niveau minder.
    """
    login(client, db_session)
    assert 'name="rollup"' not in _paneel(client, BASIS)
    diep = _paneel(client, "object=payment_created_quarter&object=payment_amount"
                           "&layout=pivot")
    assert 'name="rollup"' not in diep, (
        "ook een kwartaal zonder jaar erboven kan niet oprollen")


def test_drilling_leaves_the_sort_and_the_column_axis_alone(client, db_session,
                                                            situation):
    """Sinds #907 verhuist er niets, dus er valt niets te verslepen."""
    login(client, db_session)
    tekst = _paneel(client, "object=payment_created_year&object=payment_method"
                            "&object=payment_amount&sort=payment_created_year&dir=asc"
                            "&layout=pivot&pivot_column=payment_created_year"
                            "&drill=payment_created_quarter|2026")
    # Niets verhuist meer: het jaar blijft in het rapport, dus sorteren en de
    # kolomas blijven wijzen waar ze wezen. Dat was bij VERVANGEN wél nodig.
    assert 'name="sort" value="payment_created_year"' in tekst
    assert 'name="pivot_column" value="payment_created_year"' in tekst


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

"""Charts (#835, CR-06 §6): the crosstab, drawn.

The first test is the one that matters and it is not about looks: **the series in
the rendered SVG are the cells of the crosstab**. A chart that draws its own
numbers is the failure this design exists to prevent — and it is invisible, because
a bar is never obviously wrong by three percent.

So the values are read back out of the markup (`data-value`) and compared with the
pivot, and the pivot with the table. One number, three places.
"""
from __future__ import annotations

import re
from decimal import Decimal
from io import BytesIO

import pytest

from app.domains.reporting.api import (
    SERIES_COLORS, Selection, SelectionError, build_chart, build_pivot,
    chart_data, run_validated,
)
from tests._reporting_seed import EXPECTED, TENANT_A, seed
from tests.test_reporting_panel_ui import login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def chart_for(db, objects, kind, *, column=""):
    pivot = build_pivot(
        db,
        Selection(object_keys=tuple(objects), layout=kind, pivot_column=column,
                  limit=5000),
        tenant_id=TENANT_A)
    return pivot, build_chart(pivot, kind)


def chart_svg(html: str) -> str:
    """The chart's own SVG.

    Picked by its id and not as "the first `<svg>`": every icon in the kit is an
    SVG too, so the first one on the page is a chevron.
    """
    blokken = re.findall(r"<svg\b.*?</svg>", html, re.S)
    voor_de_grafiek = [b for b in blokken if "rp-chart-t" in b]
    assert voor_de_grafiek, "geen grafiek-SVG in het antwoord"
    return voor_de_grafiek[0]


def svg_values(html: str) -> list[tuple[str, float]]:
    """(series, value) per drawn element, straight out of the markup."""
    return [(m.group(1), float(m.group(2)))
            for m in re.finditer(r'data-series="([^"]*)" data-value="([^"]*)"', html)]


# ── One number, three places (#835 test 1) ───────────────────────────────────

def test_the_drawn_values_are_the_crosstab_s_cells(client, db_session, situation):
    """Read back out of the markup, not out of the object that produced it.

    Asserting on `chart.series` would prove that the builder is consistent with
    itself. What has to hold is that the thing on screen carries those numbers,
    so the values come out of the rendered SVG.
    """
    login(client, db_session)
    antwoord = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_amount"
        "&layout=bar")
    assert antwoord.status_code == 200

    getekend = svg_values(antwoord.text)
    assert {naam for naam, _v in getekend} == {"Te betalen"}, (
        "één maat, dus één reeks")
    assert sorted(waarde for _naam, waarde in getekend) == \
        sorted(float(bedrag) for bedrag in EXPECTED["payments"]["per_method"].values())

    # And the same numbers are in the table under it.
    for bedrag in EXPECTED["payments"]["per_method"].values():
        assert f"{bedrag:.2f}".replace(".", ",") in antwoord.text


def test_the_chart_and_the_table_form_agree(db_session, situation):
    objecten = ("payment_method", "payment_amount")
    tabel = run_validated(db_session, Selection(object_keys=objecten),
                          tenant_id=TENANT_A)
    _pivot, grafiek = chart_for(db_session, list(objecten), "bar")
    getekend = sum(v for v in grafiek.series[0].values if v is not None)
    assert Decimal(str(getekend)) == Decimal(tabel.totals["payment_amount"])


def test_the_table_keeps_rendering_under_the_chart(client, db_session, situation):
    """#835 test 6: a picture is never the only way to the number."""
    login(client, db_session)
    antwoord = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_amount"
        "&layout=line")
    assert "<svg" in antwoord.text
    assert "<table" in antwoord.text, "de tabel eronder is het tekstalternatief"
    assert "Eindtotaal" in antwoord.text
    assert "<title" in antwoord.text and "<desc" in antwoord.text


# ── Known numbers (#835 test 2) ──────────────────────────────────────────────

def test_revenue_per_month_as_a_line(db_session, situation):
    """Question 5, drawn. The months follow from when the seed ran, so what is
    asserted is what must hold anyway: the line's points add up to the total."""
    _pivot, grafiek = chart_for(db_session, ["date_month", "payment_amount"], "line")
    assert len(grafiek.series) == 1
    som = sum(v for v in grafiek.series[0].values if v is not None)
    assert Decimal(str(som)) == EXPECTED["payments"]["amount"]
    assert grafiek.money is True, "een geldmaat wordt als geld gelabeld"


def test_registrations_per_activity_per_year_as_a_stacked_bar(db_session, situation):
    """Question 3, drawn. One activity, one year, so one segment."""
    _y0, _y1, y2, _y3 = situation["years"]
    _pivot, grafiek = chart_for(
        db_session, ["activity", "activity_year", "registration_count"],
        "stacked", column="activity_year")
    assert [s.name for s in grafiek.series] == [str(y2)]
    assert grafiek.x_labels == ["Quiz"]
    assert grafiek.series[0].values == [EXPECTED["registrations"]["count"]]


def test_a_stacked_bar_reaches_the_sum_of_its_parts(db_session, situation):
    """The axis has to fit the stack, not the tallest part.

    Betaalwijze × Waarvoor stacks 10,00 on 35,00 for two methods, so the domain
    must reach 45 — an axis at 35 would clip the top of every bar without any
    error anywhere.
    """
    _pivot, grafiek = chart_for(
        db_session, ["payment_method", "payment_payable_type", "payment_amount"],
        "stacked", column="payment_payable_type")
    assert grafiek.y_max >= 45, f"as reikt tot {grafiek.y_max}, de hoogste stapel is 45"


def test_a_missing_cell_is_not_drawn_as_zero(db_session, situation):
    """Nobody paid an activity in cash, so that segment does not exist."""
    _pivot, grafiek = chart_for(
        db_session, ["payment_method", "payment_payable_type", "payment_amount"],
        "stacked", column="payment_payable_type")
    activiteit = next(s for s in grafiek.series if s.name == "Activiteit")
    cash = grafiek.x_labels.index("Cash")
    assert activiteit.values[cash] is None, (
        "een ontbrekende cel wordt niet als nul getekend")


# ── The scale ────────────────────────────────────────────────────────────────

def test_zero_is_always_in_the_domain(db_session, situation):
    """A baseline that is not zero exaggerates every difference on the chart."""
    _pivot, grafiek = chart_for(db_session, ["payment_method", "payment_amount"],
                                "bar")
    assert grafiek.y_min <= 0 <= grafiek.y_max


def test_the_axis_ends_on_a_round_number(db_session, situation):
    _pivot, grafiek = chart_for(db_session, ["payment_method", "payment_amount"],
                                "bar")
    # The tallest bar is 45,00, so a round axis stops at 50.
    assert grafiek.y_max == 50, f"as eindigt op {grafiek.y_max}"
    assert len(grafiek.y_ticks) == 5
    assert grafiek.y_ticks[0] == grafiek.y_min
    assert grafiek.y_ticks[-1] == grafiek.y_max


def test_a_negative_measure_keeps_zero_as_its_baseline(db_session, situation):
    """Refunds are negative. The axis has to go below zero, not start there."""
    _pivot, grafiek = chart_for(
        db_session, ["payment_payable_type", "payment_refunded"], "bar")
    assert grafiek.y_min <= 0 <= grafiek.y_max


# ── Colours and refusals ─────────────────────────────────────────────────────

def test_series_colours_are_tokens_and_never_raw_hex(db_session, situation):
    _pivot, grafiek = chart_for(
        db_session, ["payment_method", "payment_payable_type", "payment_amount"],
        "stacked", column="payment_payable_type")
    for reeks in grafiek.series:
        assert reeks.color.startswith("var(--"), reeks.color
        assert reeks.color in SERIES_COLORS


def test_a_stacked_bar_without_a_column_dimension_says_so(db_session, situation):
    pivot = build_pivot(
        db_session,
        Selection(object_keys=("payment_method", "payment_amount"), layout="bar"),
        tenant_id=TENANT_A)
    with pytest.raises(SelectionError) as exc:
        build_chart(pivot, "stacked")
    assert "kolomdimensie" in str(exc.value)


def test_an_unknown_chart_kind_is_refused(db_session, situation):
    pivot = build_pivot(
        db_session,
        Selection(object_keys=("payment_method", "payment_amount"), layout="bar"),
        tenant_id=TENANT_A)
    with pytest.raises(SelectionError) as exc:
        build_chart(pivot, "taart")
    assert "'taart'" in str(exc.value)


def test_subtotal_rows_are_not_drawn(db_session, situation):
    """Drawn beside their own parts they would count the same money twice."""
    _pivot, grafiek = chart_for(
        db_session, ["payment_payable_type", "payment_method", "payment_amount"],
        "bar")
    assert "Subtotaal" not in " ".join(grafiek.x_labels)
    assert len(grafiek.x_labels) == 5, "vijf combinaties, geen subtotaalstaven"


# ── The panel and the export (#835 test 3) ───────────────────────────────────

def test_all_three_kinds_render_without_a_raw_colour(client, db_session,
                                                     situation):
    """#835 test 3: no screen invents a colour, the SVG included."""
    login(client, db_session)
    for vorm in ("bar", "line", "stacked"):
        antwoord = client.get(
            "/admin/rapporten/paneel?object=payment_method"
            "&object=payment_payable_type&object=payment_amount"
            f"&layout={vorm}&pivot_column=payment_payable_type")
        assert antwoord.status_code == 200, vorm
        svg = chart_svg(antwoord.text)
        assert "<title" in svg and "<desc" in svg, vorm
        rauw = re.findall(r"(?:fill|stroke)=\"(#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))\"",
                          svg)
        assert not rauw, f"{vorm}: rauwe kleur in de SVG: {rauw}"
        assert 'fill="var(--brand-ocean)"' in svg, vorm


def test_the_export_carries_the_chart_data_on_sheet_three(client, db_session,
                                                          situation):
    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow
    from odf.text import P

    login(client, db_session)
    antwoord = client.get(
        "/admin/rapporten/export.ods?object=payment_method&object=payment_amount"
        "&layout=bar")
    assert antwoord.status_code == 200

    document = load(BytesIO(antwoord.content))
    bladen = {}
    for tabel in document.getElementsByType(Table):
        bladen[tabel.getAttribute("name")] = [
            ["".join(str(p) for p in cel.getElementsByType(P))
             for cel in rij.getElementsByType(TableCell)]
            for rij in tabel.getElementsByType(TableRow)]

    assert "Grafiek" in bladen, "blad 3 draagt de grafiekdata"
    blad3 = bladen["Grafiek"]
    assert blad3[0] == ["Categorie", "Te betalen"]
    getekend = {rij[0]: Decimal(rij[1]) for rij in blad3[1:]}
    assert getekend == EXPECTED["payments"]["per_method"]


def test_chart_data_is_the_series_as_drawn(db_session, situation):
    _pivot, grafiek = chart_for(db_session, ["payment_method", "payment_amount"],
                                "bar")
    data = chart_data(grafiek)
    assert data.headers == ["Categorie", "Te betalen"]
    assert len(data.rows) == len(grafiek.x_labels)
    assert [rij[1] for rij in data.rows] == grafiek.series[0].values


def test_a_saved_chart_keeps_its_shape(client, db_session, situation):
    from app.domains.reporting.api import list_saved_reports
    from tests.test_reporting_panel_ui import ADMIN_EMAIL

    csrf = login(client, db_session)
    client.post("/admin/rapporten",
                headers={"X-CSRF-Token": csrf,
                         "Content-Type": "application/x-www-form-urlencoded"},
                content=("name=Staafje&is_shared=1&layout=bar"
                         "&object=payment_method&object=payment_amount"))
    bewaard = [r for r in list_saved_reports(db_session, tenant_id=TENANT_A,
                                             viewer=ADMIN_EMAIL)
               if r.name == "Staafje"][0]
    assert bewaard.selection["layout"] == "bar"

    pagina = client.get(f"/admin/rapporten/{bewaard.id}")
    assert "<svg" in pagina.text
    lijst = client.get("/admin/rapporten/lijst?q=Staafje")
    assert "Staafgrafiek" in lijst.text, "de kaart toont de vorm"

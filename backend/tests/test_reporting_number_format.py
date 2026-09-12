"""Every declared format has a rendering, and none of them prints raw (#875).

Koen built a report with *Gemiddelde betaaltermijn* and got `0E-20`,
`0.29629629629629630` and `12.1000000000000000` on screen, while the money column
beside it read `€ 247,00`. `0E-20` is not a calculation error — that is how a
`Decimal` of zero with twenty decimals prints itself.

**The cause was wider than that column, and wider than reported.** The issue said
five formats; this gate found **seven** on its first run — `YEAR` and `DATE` were
declared too, and went through just as raw. A year printed by a number formatter
reads `1.999`. The panel knew one format: money. Everything else went to the screen
raw, so four of the seven were declared and ignored — the same shape as #852, where
the universe promised something the code did not keep.

**So the gate is on the mapping and not on one column.** `FORMATTERS` must cover
every value of `Format`; a new format that is not in it fails here instead of
quietly printing raw. Broken once: `days` was removed from `FORMATTERS` and
`test_every_declared_format_has_a_rendering` went red naming it, while
`test_a_days_measure_is_not_printed_raw` showed the twenty-decimal value coming
back. Both were restored.

Not touched: the ODS export. It writes `Decimal` as `float` so Calc gets a number
you can add up; turning that into text would make it useless to the treasurer.
`test_the_export_still_writes_numbers_and_not_text` holds that line.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.domains.reporting.universe import Format
from app.kernel.meetwaarden import FORMATTERS, meetwaarde
from tests._reporting_seed import TENANT_A, seed
from tests.test_reporting_panel_ui import login


@pytest.fixture
def situation(db_session):
    return seed(db_session)


def test_every_declared_format_has_a_rendering():
    """The gate. A declared format with no rendering is a promise nobody keeps."""
    gedeclareerd = {f.value for f in Format}
    assert gedeclareerd == set(FORMATTERS), (
        f"zonder weergave: {sorted(gedeclareerd - set(FORMATTERS))}; "
        f"onbekend in de universe: {sorted(set(FORMATTERS) - gedeclareerd)}")


def test_the_gate_goes_red_when_a_format_loses_its_rendering():
    """The counter-proof, run rather than described.

    What was broken: `days` was taken out of `FORMATTERS`. The assertion above
    failed naming `days`, and the value it should have formatted came back as
    `12.1000000000000000`. Putting it back made both green.
    """
    origineel = dict(FORMATTERS)
    FORMATTERS.pop("days")
    try:
        assert {f.value for f in Format} != set(FORMATTERS), (
            "met een weggehaalde soort hoort de gate te falen")
        assert meetwaarde(Decimal("12.1000000000000000"), "days") == \
            "12.1000000000000000", (
            "en dan valt hij terug op de ruwe waarde — precies wat Koen zag")
    finally:
        FORMATTERS.clear()
        FORMATTERS.update(origineel)
    assert {f.value for f in Format} == set(FORMATTERS)


def test_the_values_koen_saw_are_all_readable_now():
    """The three literal values from the report, and one Decimal(0) with decimals."""
    assert meetwaarde(Decimal("0E-20"), "days") == "0,0"
    assert meetwaarde(Decimal("0.29629629629629630"), "days") == "0,3"
    assert meetwaarde(Decimal("12.1000000000000000"), "days") == "12,1"
    assert meetwaarde(Decimal("247.00"), "money") == "247,00"


def test_a_year_is_not_a_number_with_a_thousands_separator():
    """`1.999` is what a number formatter makes of a year, so it has its own."""
    assert meetwaarde(1999, "year") == "1999"
    assert meetwaarde(Decimal("2026"), "year") == "2026"


def test_a_date_reads_the_way_every_other_admin_table_writes_it():
    from datetime import date

    assert meetwaarde(date(2026, 9, 12), "date") == "12-09-2026"


def test_a_count_has_no_decimals():
    """A half member does not exist."""
    assert meetwaarde(Decimal("4"), "count") == "4"
    assert meetwaarde(Decimal("4.0000"), "count") == "4"
    assert meetwaarde(4, "count") == "4"


def test_nothing_is_rendered_as_nothing():
    """An empty cell stays empty, and never becomes "None" or "0"."""
    assert meetwaarde(None, "money") == ""
    assert meetwaarde(None, "days") == ""


def test_a_days_measure_is_not_printed_raw(client, db_session, situation):
    """End to end, because the panel was the place that got it wrong.

    `Gemiddelde betaaltermijn` is an `AVG`, so it is exactly the column that
    produced a twenty-decimal Decimal.
    """
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=payment_method"
        "&object=payment_days_to_paid")
    assert fragment.status_code == 200
    assert "0E-20" not in fragment.text
    assert "0000000" not in fragment.text, (
        "een rauwe Decimal op het scherm; de opmaak van deze soort wordt "
        "genegeerd")


def test_the_totals_row_formats_the_same_way_as_the_rows(client, db_session,
                                                         situation):
    """The formatting used to sit in three places, each with its own money branch.

    Three copies round differently on the day one of them is edited, so this
    asserts they agree rather than asserting a particular string.
    """
    login(client, db_session)
    fragment = client.get(
        "/admin/rapporten/paneel?object=payment_method&object=payment_amount").text
    # The money format writes a comma and a euro sign, in the rows and in the
    # totals row alike. Counting is enough: if one branch reverts to raw, the
    # euro signs no longer match the number of money cells.
    assert fragment.count("€") >= 2, "zowel de rijen als de totaalrij"
    assert ".00" not in fragment.replace(".000", ""), (
        "een punt als decimaalteken hoort er niet te staan (#735)")


def test_the_export_still_writes_numbers_and_not_text(db_session, situation):
    """The line #875 must not cross.

    The ODS export writes a `Decimal` as a float so Calc gets a value you can add
    up. Formatting it as text would make the sheet unusable for the treasurer —
    so the formatter belongs to the screen, and this test says so out loud.
    """
    import io
    import zipfile

    from app.domains.reporting.api import (Selection, build_report_ods,
                                           run_validated)

    selectie = Selection(object_keys=("payment_method", "payment_amount"))
    resultaat = run_validated(db_session, selectie, tenant_id=TENANT_A)
    inhoud = build_report_ods(db_session, resultaat, selectie,
                              title="Test", tenant_id=TENANT_A)
    with zipfile.ZipFile(io.BytesIO(inhoud)) as zf:
        xml = zf.read("content.xml").decode()
    assert 'office:value-type="float"' in xml, (
        "bedragen horen als getal in het blad te staan, niet als tekst")

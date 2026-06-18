"""Formule-/CSV-injectie in .ods-exports neutraliseren (#270): publiek ingevoerde
namen mogen niet als formule uitgevoerd worden wanneer een admin de export opent."""
from io import BytesIO

from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.teletype import extractText

from app.services.ods_export import _neutralize, build_ods


def test_neutralize_quotes_formula_triggers():
    for payload in ('=HYPERLINK("x")', "+1+1", "-2", "@SUM(A1)", "\tx", "\rx"):
        assert _neutralize(payload) == "'" + payload


def test_neutralize_leaves_plain_text():
    assert _neutralize("Jan Janssen") == "Jan Janssen"
    assert _neutralize("") == ""
    assert _neutralize("0470 12 34 56") == "0470 12 34 56"


def _data_cell(raw: bytes):
    table = load(BytesIO(raw)).getElementsByType(Table)[0]
    # rij 0 = kopregel, rij 1 = eerste datarij
    return table.getElementsByType(TableRow)[1].getElementsByType(TableCell)[0]


def test_build_ods_neutralizes_formula_in_cell():
    raw = build_ods("Blad1", ["Naam"], [['=HYPERLINK("https://evil")']])
    assert extractText(_data_cell(raw)).startswith("'=HYPERLINK")


def test_build_ods_leaves_number_untouched():
    cell = _data_cell(build_ods("Blad1", ["Bedrag"], [[30]]))
    assert cell.getAttribute("value") == "30"
    assert not extractText(cell).startswith("'")

"""Veiligheid van de .ods-export tegen formule-/CSV-injectie (#270 → gecorrigeerd in #288).

Correctie: voor een NATIVE .ods schrijven we elke cel als type ``string``; Calc/
Excel voeren string-cellen NOOIT als formule uit, dus dat celtype IS de
bescherming. De eerdere apostrof-prefix (een CSV-mitigatie) is teruggedraaid: hij
voegde geen beveiliging toe op .ods en corrumpeerde legitieme waarden (een
zichtbare leidende ``'``, en mobiele nummers als ``+32…`` werden ``'+32…``).
"""
from io import BytesIO

from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.teletype import extractText

from app.services.ods_export import build_ods


def _data_cell(raw: bytes):
    table = load(BytesIO(raw)).getElementsByType(Table)[0]
    # rij 0 = kopregel, rij 1 = eerste datarij
    return table.getElementsByType(TableRow)[1].getElementsByType(TableCell)[0]


def test_build_ods_writes_string_values_verbatim():
    """Geen apostrof-prefix meer: formule-achtige tekst én telefoonnummers worden
    letterlijk geschreven (geen datacorruptie)."""
    for raw_value in ('=HYPERLINK("https://evil")', "+32470123456", "-5", "@cmd"):
        cell = _data_cell(build_ods("Blad1", ["Waarde"], [[raw_value]]))
        assert extractText(cell) == raw_value
        assert not extractText(cell).startswith("'")


def test_build_ods_formula_cell_is_string_typed_not_executed():
    """De bescherming zit in het celtype: een formule-achtige waarde komt als
    value-type=string in de .ods en wordt dus nooit als formule uitgevoerd."""
    cell = _data_cell(build_ods("Blad1", ["Naam"], [["=1+1"]]))
    assert cell.getAttribute("valuetype") == "string"
    assert extractText(cell) == "=1+1"  # letterlijk, niet "2"


def test_build_ods_leaves_number_untouched():
    cell = _data_cell(build_ods("Blad1", ["Bedrag"], [[30]]))
    assert cell.getAttribute("value") == "30"
    assert not extractText(cell).startswith("'")

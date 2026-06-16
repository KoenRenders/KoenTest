"""Tests voor de rapport-parsing (#201): .ods lezen + format-detectie.

Het ledenrapport komt in twee gelijkwaardige formaten binnen (.xls en .ods).
Hier genereren we in-memory een .ods met odfpy en controleren dat de parser er
dezelfde rij-/gezinsstructuur uit haalt, inclusief de geboortedatum. Het formaat
wordt uit de bytes gesnuffeld, niet uit de bestandsnaam.
"""
import io
import zipfile
from datetime import date

import pytest

from app.services.ledenrapport import (
    parse_families,
    read_ledenrapport_bytes,
    _detect_format,
)


def _ods_row(lidnr, voornaam, naam, huisnr, email, gsm, dob, geslacht, soort):
    """16 kolommen in de rapportvolgorde (index 14 ongebruikt)."""
    return [lidnr, voornaam, naam, "Milostraat", huisnr, "", "2400", "Mol",
            email, "", gsm, dob, geslacht, "", "", soort]


def _make_ods(rows):
    """Bouw een .ods (bytes) met 4 kop-rijen + de gegeven datarijen."""
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableRow, TableCell
    from odf.text import P

    doc = OpenDocumentSpreadsheet()
    table = Table(name="Sheet1")
    for _ in range(4):                       # 4 kop-rijen zoals het echte rapport
        tr = TableRow()
        tc = TableCell(valuetype="string")
        tc.addElement(P(text="kop"))
        tr.addElement(tc)
        table.addElement(tr)
    for row in rows:
        tr = TableRow()
        for idx, val in enumerate(row):
            if idx == 11 and isinstance(val, date):
                tc = TableCell(valuetype="date", datevalue=val.isoformat())
                tc.addElement(P(text=val.isoformat()))
            else:
                tc = TableCell(valuetype="string")
                tc.addElement(P(text="" if val is None else str(val)))
            tr.addElement(tc)
        table.addElement(tr)
    doc.spreadsheet.addElement(table)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_ods_detected_and_parsed_to_families():
    content = _make_ods([
        _ods_row("100", "Jan", "Janssens", "40", "Jan@Example.com",
                 "0470 12 34 56", date(1980, 5, 1), "M", "lid"),
        _ods_row("101", "An", "Janssens", "40", "", "", date(1982, 3, 3), "V", "partner"),
    ])

    assert _detect_format(content) == "ods"

    families, bl_index, names, rows = parse_families(content, load_all=True)
    assert len(rows) == 2
    assert len(families) == 1                 # zelfde adres → één gezin

    fam = families[0]
    assert fam[0]["_relatie"] == "HOOFDLID"   # gesorteerd: hoofdlid eerst
    hoofd = next(r for r in fam if r["lidnr"] == "100")
    assert hoofd["voornaam"] == "Jan"
    assert hoofd["email"] == "jan@example.com"        # lowercased
    assert hoofd["gsm"] == "0470123456"               # spaties verwijderd
    assert hoofd["geboortedatum"] == date(1980, 5, 1)  # datum uit office:date-value
    assert hoofd["geslacht"] == "M"

    partner = next(r for r in fam if r["lidnr"] == "101")
    assert partner["geslacht"] == "F"
    assert partner["geboortedatum"] == date(1982, 3, 3)


def test_ods_blank_first_column_rows_skipped():
    content = _make_ods([
        _ods_row("100", "Jan", "Janssens", "40", "", "", date(1980, 5, 1), "M", "lid"),
        _ods_row("", "", "", "", "", "", None, "", ""),   # lege rij → genegeerd
    ])
    _, _, _, rows = parse_families(content, load_all=True)
    assert len(rows) == 1


def test_detect_format_xls_magic():
    assert _detect_format(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"rest") == "xls"


def test_xlsx_is_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<x/>")
        z.writestr("xl/workbook.xml", "<x/>")
    content = buf.getvalue()
    assert _detect_format(content) == "xlsx"
    with pytest.raises(ValueError):
        read_ledenrapport_bytes(content)


def test_unknown_bytes_rejected():
    assert _detect_format(b"dit is geen rekenblad") == "unknown"
    with pytest.raises(ValueError):
        read_ledenrapport_bytes(b"dit is geen rekenblad")

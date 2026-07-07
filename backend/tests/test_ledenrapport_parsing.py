"""Tests voor de rapport-parsing (#201, #231): .ods lezen + format-detectie +
header-gebaseerde kolom-mapping.

Het ledenrapport komt in twee gelijkwaardige formaten binnen (.xls en .ods). We
genereren in-memory een .ods met een **echte header-rij** en controleren dat de
parser elk veld op zijn koptekst leest — robuust voor extra of herschikte kolommen
(#231: anders werd een kind als hoofdlid geïmporteerd). Het formaat wordt uit de
bytes gesnuffeld, niet uit de bestandsnaam.
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

# Kolomnamen zoals het Raak-Nationaal-rapport ze in de header-rij zet.
_STD_HEADERS = [
    "Lidnummer", "Voornaam", "Naam", "Straat", "Huisnummer", "Busnummer",
    "Postcode", "Gemeente", "E-mail adres", "Telefoon", "GSM", "Geboortedatum",
    "Geslacht", "Verantwoordelijk bestuurslid2", "Soort lid",
]


def _person(lidnr, voornaam, naam, dob, geslacht, soort, *, huisnr="40", email="", gsm=""):
    """Eén lid als {kolomnaam: waarde}; ontbrekende kolommen blijven leeg."""
    return {
        "Lidnummer": lidnr, "Voornaam": voornaam, "Naam": naam,
        "Straat": "Milostraat", "Huisnummer": huisnr, "Postcode": "2400",
        "Gemeente": "Mol", "E-mail adres": email, "GSM": gsm,
        "Geboortedatum": dob, "Geslacht": geslacht, "Soort lid": soort,
    }


def _make_ods(headers, rows, *, lead=3):
    """Bouw een .ods (bytes): `lead` titel-rijen + een header-rij + datarijen.
    Elke datarij is een {kolomnaam: waarde}; cellen worden in `headers`-volgorde
    geschreven (zo kan de kolomvolgorde vrij gekozen worden)."""
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableRow, TableCell
    from odf.text import P

    def _cell(val):
        if isinstance(val, date):
            tc = TableCell(valuetype="date", datevalue=val.isoformat())
            tc.addElement(P(text=val.isoformat()))
        else:
            tc = TableCell(valuetype="string")
            tc.addElement(P(text="" if val is None else str(val)))
        return tc

    doc = OpenDocumentSpreadsheet()
    table = Table(name="Sheet1")
    for _ in range(lead):                       # titel-rijen (bv. 'Uw selectiecriteria')
        tr = TableRow()
        tr.addElement(_cell("titel"))
        table.addElement(tr)
    hr = TableRow()                             # header-rij met kolomnamen
    for h in headers:
        hr.addElement(_cell(h))
    table.addElement(hr)
    for row in rows:                            # datarijen
        tr = TableRow()
        for h in headers:
            tr.addElement(_cell(row.get(h)))
        table.addElement(tr)
    doc.spreadsheet.addElement(table)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_ods_detected_and_parsed_to_families():
    content = _make_ods(_STD_HEADERS, [
        _person("100", "Jan", "Janssens", date(1980, 5, 1), "M", "lid",
                email="Jan@Example.com", gsm="0470 12 34 56"),
        _person("101", "An", "Janssens", date(1982, 3, 3), "V", "partner"),
    ])

    assert _detect_format(content) == "ods"

    families, bl_index, names, rows = parse_families(content)
    assert len(rows) == 2
    assert len(families) == 1                 # zelfde adres → één gezin

    fam = families[0]
    assert fam[0]["_relatie"] == "HOOFDLID"   # gesorteerd: hoofdlid eerst
    hoofd = next(r for r in fam if r["lidnr"] == "100")
    assert hoofd["voornaam"] == "Jan"
    assert hoofd["email"] == "jan@example.com"        # lowercased
    assert hoofd["gsm"] == "0470123456"               # spaties verwijderd
    assert hoofd["geboortedatum"] == date(1980, 5, 1)
    assert hoofd["geslacht"] == "M"

    partner = next(r for r in fam if r["lidnr"] == "101")
    assert partner["geslacht"] == "F"
    assert partner["geboortedatum"] == date(1982, 3, 3)


def test_ods_blank_rows_skipped():
    content = _make_ods(_STD_HEADERS, [
        _person("100", "Jan", "Janssens", date(1980, 5, 1), "M", "lid"),
        {},                                            # lege rij → genegeerd
    ])
    _, _, _, rows = parse_families(content)
    assert len(rows) == 1


def test_ods_extra_and_reordered_columns_map_by_header():
    """#231: extra/herschikte kolommen breken de import niet — relatie en geslacht
    worden op koptekst gelezen, niet op positie. Een kind blijft KIND (en wordt
    geen hoofdlid), ook al staat het eerst in het bestand."""
    headers = [
        "Lidnummer", "Voornaam", "Naam", "Straat", "Huisnummer", "Busnummer",
        "Postcode", "Gemeente", "E-mail adres", "Telefoon", "GSM", "Geboortedatum",
        "Lid sinds", "Geslacht", "Ledenblad", "Datum creatie",
        "Verantwoordelijk bestuurslid2", "Soort lid", "Functie",   # extra kolommen ertussen
    ]
    content = _make_ods(headers, [
        _person("201", "Tom", "Janssens", date(2008, 2, 2), "M", "(meerderjarig) kind"),  # kind eerst
        _person("100", "Jan", "Janssens", date(1980, 5, 1), "M", "lid"),                  # hoofdlid
    ])

    families, _bl, _names, _rows = parse_families(content)
    assert len(families) == 1
    fam = families[0]
    assert fam[0]["_relatie"] == "HOOFDLID"               # correct gesorteerd ondanks volgorde
    hoofd = next(r for r in fam if r["lidnr"] == "100")
    kind = next(r for r in fam if r["lidnr"] == "201")
    assert hoofd["soort"] == "lid" and hoofd["_relatie"] == "HOOFDLID"
    assert kind["soort"] == "(meerderjarig) kind" and kind["_relatie"] == "KIND"
    assert hoofd["geslacht"] == "M"                        # geslacht uit de JUISTE kolom


def test_ods_missing_required_column_raises():
    """Ontbreekt een verplichte kolom (bv. Lidnummer), dan een duidelijke fout."""
    headers = ["Voornaam", "Naam", "Straat", "Huisnummer", "Postcode",
               "Gemeente", "Geboortedatum", "Soort lid"]               # geen Lidnummer
    content = _make_ods(headers, [
        _person("100", "Jan", "Janssens", date(1980, 5, 1), "M", "lid"),
    ])
    with pytest.raises(ValueError):
        read_ledenrapport_bytes(content)


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

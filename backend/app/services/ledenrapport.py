"""Parsing van het Raak-Nationaal-ledenrapport naar gezinnen.

Het rapport komt als rekenblad binnen in **twee gelijkwaardige formaten**:

  - ``.xls``  — het klassieke Excel-formaat (gelezen met ``xlrd``);
  - ``.ods``  — OpenDocument Spreadsheet / LibreOffice Calc (gelezen met ``odfpy``).

Beide leveren exact dezelfde rij-dicts en dus dezelfde gezinsstructuur op; het
formaat wordt **gesnuffeld uit de bytes** (OLE2 vs. ZIP/ODS), niet uit de
bestandsnaam, zodat ook stappen zonder filename (bv. de commit-stap van de
upload) werken.

Gedeeld tussen het CLI-script (``import_leden.py``) en het admin-upload-endpoint
(``app/routers/member_import.py``), zodat er maar één plek is die de rapportvorm
kent. De upsert zelf zit in :mod:`app.services.member_import`.

De kolomvolgorde is identiek voor beide formaten; alleen het uitlezen van de
cellen en de datums verschilt (Excel bewaart een serienummer, ODS een ISO-datum).
"""
import io
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime

import xlrd

# Testadressen voor niet-PROD omgevingen (straat lowercase, huisnummer exact).
TEST_ADDRESSES = [
    ("kerkebossenstraat", "21"),
    ("milostraat", "40"),
]

# Relatie-mapping rapport → DB-code.
RELATIE_MAP = {
    "lid": "HOOFDLID",
    "partner": "PARTNER",
    "(meerderjarig) kind": "KIND",
}

# Sorteervolgorde voor relaties binnen een gezin (hoofdlid eerst).
RELATIE_ORDER = {"HOOFDLID": 0, "PARTNER": 1, "KIND": 2}

# Aantal kolommen dat de rij-mapping verwacht (t/m kolom 15 = 'soort').
_NUM_COLS = 16


def normalize(s: str) -> str:
    """Verwijder overbodige spaties en zet om naar lowercase."""
    return re.sub(r"\s+", " ", str(s).strip()).strip()


def parse_gender(v: str) -> str | None:
    """Zet 'V'→'F', 'M'→'M'. Onbekend → None."""
    v = v.strip().upper()
    if v == "V":
        return "F"
    if v == "M":
        return "M"
    return None


def clean_phone(v: str) -> str | None:
    """Verwijder spaties/slashes; geef None terug als leeg."""
    v = re.sub(r"\s+", "", v.strip())
    return v if v else None


def _row_from_values(v: list) -> dict:
    """Bouw één genormaliseerde rij-dict uit een lijst celwaarden.

    ``v`` is format-onafhankelijk: ``v[11]`` (geboortedatum) is door de
    format-specifieke reader al naar een ``date | None`` omgezet; de overige
    cellen zijn ruwe waarden. De lijst is minstens ``_NUM_COLS`` lang (gepad).
    """
    return {
        "lidnr":         str(v[0]).strip(),
        "voornaam":      normalize(v[1]),
        "naam":          normalize(v[2]),
        "straat":        normalize(v[3]),
        "huisnummer":    normalize(v[4]),
        "busnummer":     normalize(v[5]),
        "postcode":      str(v[6]).strip(),
        "gemeente":      normalize(v[7]),
        "email":         normalize(v[8]).lower() or None,
        "telefoon":      clean_phone(str(v[9])),
        "gsm":           clean_phone(str(v[10])),
        "geboortedatum": v[11],                       # reeds date | None
        "geslacht":      parse_gender(str(v[12])),
        "bestuurslid":   normalize(v[13]) or None,    # "NAAM Voornaam"
        "soort":         normalize(v[15]).lower(),    # lid / partner / kind
    }


def _pad(values: list, n: int) -> list:
    """Pad een rij tot minstens ``n`` cellen met lege strings."""
    if len(values) >= n:
        return values
    return list(values) + [""] * (n - len(values))


# ── Excel (.xls) ─────────────────────────────────────────────────────────────

def _xls_date(serial, datemode: int) -> date | None:
    """Converteer een Excel-datumserienummer naar een Python date."""
    if not serial:
        return None
    try:
        return xlrd.xldate.xldate_as_datetime(serial, datemode).date()
    except Exception:
        return None


def _rows_from_xls(content: bytes) -> list[dict]:
    wb = xlrd.open_workbook(file_contents=content)
    sh = wb.sheet_by_name("Sheet1")
    rows = []
    for r in range(4, sh.nrows):
        raw = [sh.cell_value(r, c) for c in range(sh.ncols)]
        if not str(raw[0]).strip():
            continue
        vals = _pad(list(raw), _NUM_COLS)
        vals[11] = _xls_date(raw[11] if len(raw) > 11 else None, wb.datemode)
        rows.append(_row_from_values(vals))
    return rows


# ── OpenDocument (.ods) ──────────────────────────────────────────────────────

def _ods_cell_text(cell) -> str:
    """Tekstinhoud van een ODS-cel (lege string bij None)."""
    if cell is None:
        return ""
    from odf import teletype
    return teletype.extractText(cell)


def _ods_date(cell) -> date | None:
    """Datum uit een ODS-cel: eerst office:date-value, dan de zichtbare tekst."""
    if cell is None:
        return None
    from odf.namespaces import OFFICENS
    dv = cell.getAttrNS(OFFICENS, "date-value")
    if dv:
        try:
            return date.fromisoformat(dv[:10])
        except ValueError:
            pass
    txt = _ods_cell_text(cell).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
    return None


def _ods_expand_cells(tr) -> list:
    """Cellen van een rij, met ``number-columns-repeated`` uitgeklapt zodat de
    kolomindexen kloppen (ODS comprimeert herhaalde/lege cellen)."""
    from odf.namespaces import TABLENS
    from odf.table import TableCell
    out: list = []
    for c in tr.getElementsByType(TableCell):
        rep = c.getAttrNS(TABLENS, "number-columns-repeated")
        n = min(int(rep), 64) if rep else 1   # cap: ons blad heeft 16 kolommen
        out.extend([c] * n)
    return out


def _find_ods_sheet(doc):
    """Sheet 'Sheet1' uit het document, met terugval op het eerste blad."""
    from odf.namespaces import TABLENS
    from odf.table import Table
    tables = doc.getElementsByType(Table)
    if not tables:
        raise ValueError("Geen blad gevonden in het .ods-bestand.")
    for t in tables:
        if t.getAttrNS(TABLENS, "name") == "Sheet1":
            return t
    return tables[0]


def _rows_from_ods(content: bytes) -> list[dict]:
    from odf.opendocument import load
    from odf.table import TableRow
    doc = load(io.BytesIO(content))
    sheet = _find_ods_sheet(doc)
    rows = []
    for i, tr in enumerate(sheet.getElementsByType(TableRow)):
        if i < 4:                       # zelfde 4 kop-rijen als bij .xls
            continue
        cells = _ods_expand_cells(tr)
        if not cells or not _ods_cell_text(cells[0]).strip():
            continue
        vals = []
        for idx in range(_NUM_COLS):
            cell = cells[idx] if idx < len(cells) else None
            vals.append(_ods_date(cell) if idx == 11 else _ods_cell_text(cell))
        rows.append(_row_from_values(vals))
    return rows


# ── Format-detectie + publieke readers ───────────────────────────────────────

def _detect_format(content: bytes) -> str:
    """Bepaal het rapportformaat uit de bytes: 'xls', 'ods', 'xlsx' of 'unknown'."""
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":   # OLE2 → oud Excel
        return "xls"
    if content[:4] == b"PK\x03\x04":                          # ZIP → ods of xlsx
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                names = z.namelist()
                mt = z.read("mimetype").decode("ascii", "ignore") if "mimetype" in names else ""
                if "opendocument.spreadsheet" in mt:
                    return "ods"
                if "[Content_Types].xml" in names or any(n.startswith("xl/") for n in names):
                    return "xlsx"
        except Exception:
            return "unknown"
    return "unknown"


def read_ledenrapport_bytes(content: bytes) -> list[dict]:
    """Lees het ledenrapport uit ruwe bytes; kiest de parser op formaat."""
    fmt = _detect_format(content)
    if fmt == "ods":
        return _rows_from_ods(content)
    if fmt == "xls":
        return _rows_from_xls(content)
    if fmt == "xlsx":
        raise ValueError("Het .xlsx-formaat wordt niet ondersteund; gebruik .xls of .ods.")
    raise ValueError("Onbekend bestandsformaat; verwacht een .xls- of .ods-ledenrapport.")


def read_ledenrapport(path: str) -> list[dict]:
    """Lees het ledenrapport van schijf (CLI)."""
    with open(path, "rb") as f:
        return read_ledenrapport_bytes(f.read())


# ── Groeperen + indexen (format-onafhankelijk) ───────────────────────────────

def group_families(rows: list[dict]) -> list[list[dict]]:
    """Groepeer personen per adres. Sorteer per gezin: HOOFDLID eerst."""
    fams: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r["straat"].lower(), r["huisnummer"].lower(),
               r["busnummer"].lower(), r["postcode"])
        r["_relatie"] = RELATIE_MAP.get(r["soort"], "KIND")
        fams[key].append(r)
    result = []
    for members in fams.values():
        members.sort(key=lambda m: RELATIE_ORDER.get(m["_relatie"], 2))
        result.append(members)
    return result


def filter_test(families: list[list[dict]]) -> list[list[dict]]:
    """Houd enkel testadressen over (veiligheidsnet buiten PROD)."""
    out = []
    for fam in families:
        straat = fam[0]["straat"].lower()
        huisnr = fam[0]["huisnummer"].lower()
        if any(straat == t[0] and huisnr == t[1] for t in TEST_ADDRESSES):
            out.append(fam)
    return out


def build_bestuurslid_index(rows: list[dict]) -> dict[str, list[dict]]:
    """Index van "NAAM Voornaam" (genormaliseerd) → lijst van rijen.

    Meerdere rijen per naam = dubbelganger → wordt gewaarschuwd.
    """
    idx: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = f"{r['naam']} {r['voornaam']}"
        idx[normalize(key)].append(r)
    return idx


def all_board_member_names(rows: list[dict]) -> list[str]:
    """Gesorteerde, unieke lijst van genormaliseerde bestuurslid-namen."""
    return sorted(set(
        normalize(r["bestuurslid"]) for r in rows if r["bestuurslid"]
    ))


def parse_families(content: bytes, *, load_all: bool):
    """High-level: bytes → (families, bl_index, all_bl_names, rows).

    Past het testadres-filter toe wanneer ``load_all`` False is. Wordt door het
    upload-endpoint gebruikt; het CLI roept de losse functies aan voor zijn
    eigen tussenrapportage.
    """
    rows = read_ledenrapport_bytes(content)
    families = group_families(rows)
    if not load_all:
        families = filter_test(families)
    return families, build_bestuurslid_index(rows), all_board_member_names(rows), rows

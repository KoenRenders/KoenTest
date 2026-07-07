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

Kolommen worden op hun **header (koptekst)** gemapt, niet op een vaste positie —
zo breken extra of herschikte kolommen in de export de import niet (#231). Alleen
het uitlezen van de cellen en de datums verschilt per formaat (Excel bewaart een
serienummer, ODS een ISO-datum).
"""
import io
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime

import xlrd

# Relatie-mapping rapport → DB-code.
RELATIE_MAP = {
    "lid": "HOOFDLID",
    "partner": "PARTNER",
    "(meerderjarig) kind": "KIND",
}

# Sorteervolgorde voor relaties binnen een gezin (hoofdlid eerst).
RELATIE_ORDER = {"HOOFDLID": 0, "PARTNER": 1, "KIND": 2}

# ── Kolommen op naam (robuust voor extra/herschikte kolommen, #231) ───────────
# Het Raak-Nationaal-rapport heeft een header-rij; we mappen elk veld op zijn
# koptekst i.p.v. op een vaste positie, zodat extra of herschikte kolommen de
# import niet meer kapotmaken. Sleutels zijn genormaliseerde (lowercase) koppen.
_HEADER_ALIASES: dict[str, set[str]] = {
    "lidnr":         {"lidnummer"},
    "voornaam":      {"voornaam"},
    "naam":          {"naam"},
    "straat":        {"straat"},
    "huisnummer":    {"huisnummer"},
    "busnummer":     {"busnummer"},
    "postcode":      {"postcode"},
    "gemeente":      {"gemeente"},
    "email":         {"e-mail adres", "e-mailadres", "email", "e-mail"},
    "telefoon":      {"telefoon"},
    "gsm":           {"gsm"},
    "geboortedatum": {"geboortedatum"},
    "geslacht":      {"geslacht"},
    "bestuurslid":   {"verantwoordelijk bestuurslid2", "verantwoordelijk bestuurslid", "bestuurslid"},
    "soort":         {"soort lid", "soort"},
}
# Verplicht aanwezig om een geldige header-rij te zijn (en voor een correcte import).
_REQUIRED_FIELDS = {
    "lidnr", "voornaam", "naam", "straat", "huisnummer", "postcode",
    "gemeente", "geboortedatum", "soort",
}


def normalize(s: str) -> str:
    """Verwijder overbodige spaties (geen lowercasing — dat doen de callers zelf)."""
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


def _xls_str(v) -> str:
    """Celwaarde → string; een geheel float (lidnummer/postcode/huisnr) zonder '.0'."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return "" if v is None else str(v)


def _build_colmap(header_texts: list[str]) -> dict[str, int]:
    """Map veld → kolomindex door elke koptekst (genormaliseerd + lowercase) tegen
    de aliassen te leggen. Bevat enkel de gevonden velden (exacte match)."""
    norm = [normalize(h).lower() for h in header_texts]
    colmap: dict[str, int] = {}
    for field, aliases in _HEADER_ALIASES.items():
        for i, h in enumerate(norm):
            if h in aliases:
                colmap[field] = i
                break
    return colmap


def _locate_header(text_rows: list[list[str]]) -> tuple[dict[str, int], int]:
    """Vind de header-rij (eerste rij met álle verplichte kolommen) en geef
    (colmap, index van de eerste datarij) terug. Duidelijke fout als de header
    ontbreekt of een verplichte kolom hernoemd is."""
    best_score, best_map = -1, {}
    for i, row in enumerate(text_rows):
        colmap = _build_colmap(row)
        score = len(_REQUIRED_FIELDS & colmap.keys())
        if score > best_score:
            best_score, best_map = score, colmap
        if score == len(_REQUIRED_FIELDS):
            return colmap, i + 1
    if best_score >= 4:
        missing = ", ".join(sorted(_REQUIRED_FIELDS - best_map.keys()))
        raise ValueError(
            "Header-rij gevonden maar verplichte kolommen ontbreken of zijn "
            f"hernoemd: {missing}. Verwacht o.a. 'Lidnummer', 'Soort lid', 'Geboortedatum'."
        )
    raise ValueError(
        "Geen header-rij met de verwachte kolommen gevonden; is dit een "
        "Raak-Nationaal-ledenrapport (.xls/.ods)?"
    )


def _row_from_cells(cells: list, colmap: dict[str, int], *, to_text, to_date) -> dict:
    """Bouw één genormaliseerde rij-dict door per veld de juiste kolom te lezen
    (op naam, via ``colmap``). ``to_text``/``to_date`` zijn format-specifiek."""
    def g(field: str) -> str:
        i = colmap.get(field)
        return to_text(cells[i]) if i is not None and i < len(cells) else ""

    gb_i = colmap.get("geboortedatum")
    geboortedatum = to_date(cells[gb_i]) if gb_i is not None and gb_i < len(cells) else None

    return {
        "lidnr":         g("lidnr").strip(),
        "voornaam":      normalize(g("voornaam")),
        "naam":          normalize(g("naam")),
        "straat":        normalize(g("straat")),
        "huisnummer":    normalize(g("huisnummer")),
        "busnummer":     normalize(g("busnummer")),
        "postcode":      g("postcode").strip(),
        "gemeente":      normalize(g("gemeente")),
        "email":         normalize(g("email")).lower() or None,
        "telefoon":      clean_phone(g("telefoon")),
        "gsm":           clean_phone(g("gsm")),
        "geboortedatum": geboortedatum,
        "geslacht":      parse_gender(g("geslacht")),
        "bestuurslid":   normalize(g("bestuurslid")) or None,
        "soort":         normalize(g("soort")).lower(),   # lid / partner / kind
    }


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
    sh = wb.sheet_by_index(0)
    raw_rows = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
    text_rows = [[_xls_str(v) for v in row] for row in raw_rows]
    colmap, data_start = _locate_header(text_rows)

    def to_date(v):
        return _xls_date(v, wb.datemode)

    rows = []
    for raw in raw_rows[data_start:]:
        row = _row_from_cells(raw, colmap, to_text=_xls_str, to_date=to_date)
        if row["lidnr"]:            # lege/voet-rijen overslaan
            rows.append(row)
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
        n = min(int(rep), 128) if rep else 1   # cap tegen enorme herhaal-runs
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
    cell_rows = [_ods_expand_cells(tr) for tr in sheet.getElementsByType(TableRow)]
    text_rows = [[_ods_cell_text(c) for c in cells] for cells in cell_rows]
    colmap, data_start = _locate_header(text_rows)

    rows = []
    for cells in cell_rows[data_start:]:
        row = _row_from_cells(cells, colmap, to_text=_ods_cell_text, to_date=_ods_date)
        if row["lidnr"]:            # lege/voet-rijen overslaan
            rows.append(row)
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


def parse_families(content: bytes):
    """High-level: bytes → (families, bl_index, all_bl_names, rows).

    Verwerkt altijd het volledige rapport (#377); de droogloop→commit-wizard is
    het veiligheidsmechanisme.
    """
    rows = read_ledenrapport_bytes(content)
    families = group_families(rows)
    return families, build_bestuurslid_index(rows), all_board_member_names(rows), rows

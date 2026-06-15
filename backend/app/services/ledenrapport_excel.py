"""Parsing van het Raak-Nationaal-ledenrapport (.xls) naar gezinnen.

Gedeeld tussen het CLI-script (``import_leden.py``) en het admin-upload-endpoint
(``app/routers/member_import.py``), zodat er maar één plek is die de Excel-vorm
kent. De upsert zelf zit in :mod:`app.services.member_import`.
"""
import re
from collections import defaultdict
from datetime import date

import xlrd

# Testadressen voor niet-PROD omgevingen (straat lowercase, huisnummer exact).
TEST_ADDRESSES = [
    ("kerkebossenstraat", "21"),
    ("milostraat", "40"),
]

# Relatie-mapping Excel → DB-code.
RELATIE_MAP = {
    "lid": "HOOFDLID",
    "partner": "PARTNER",
    "(meerderjarig) kind": "KIND",
}

# Sorteervolgorde voor relaties binnen een gezin (hoofdlid eerst).
RELATIE_ORDER = {"HOOFDLID": 0, "PARTNER": 1, "KIND": 2}


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


def parse_date(serial: float, datemode: int) -> date | None:
    """Converteer een Excel-datumserienummer naar een Python date."""
    if not serial:
        return None
    try:
        return xlrd.xldate.xldate_as_datetime(serial, datemode).date()
    except Exception:
        return None


def clean_phone(v: str) -> str | None:
    """Verwijder spaties/slashes; geef None terug als leeg."""
    v = re.sub(r"\s+", "", v.strip())
    return v if v else None


def _rows_from_workbook(wb) -> list[dict]:
    sh = wb.sheet_by_name("Sheet1")
    rows = []
    for r in range(4, sh.nrows):
        v = [sh.cell_value(r, c) for c in range(sh.ncols)]
        if not str(v[0]).strip():
            continue
        rows.append({
            "lidnr":       str(v[0]).strip(),
            "voornaam":    normalize(v[1]),
            "naam":        normalize(v[2]),
            "straat":      normalize(v[3]),
            "huisnummer":  normalize(v[4]),
            "busnummer":   normalize(v[5]),
            "postcode":    str(v[6]).strip(),
            "gemeente":    normalize(v[7]),
            "email":       normalize(v[8]).lower() or None,
            "telefoon":    clean_phone(str(v[9])),
            "gsm":         clean_phone(str(v[10])),
            "geboortedatum": parse_date(v[11], wb.datemode),
            "geslacht":    parse_gender(str(v[12])),
            "bestuurslid": normalize(v[13]) or None,   # "NAAM Voornaam"
            "soort":       normalize(v[15]).lower(),   # lid / partner / kind
        })
    return rows


def read_excel(path: str) -> list[dict]:
    """Lees het ledenrapport van schijf (CLI)."""
    return _rows_from_workbook(xlrd.open_workbook(path))


def read_excel_bytes(content: bytes) -> list[dict]:
    """Lees het ledenrapport uit ruwe bytes (upload-endpoint)."""
    return _rows_from_workbook(xlrd.open_workbook(file_contents=content))


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
    rows = read_excel_bytes(content)
    families = group_families(rows)
    if not load_all:
        families = filter_test(families)
    return families, build_bestuurslid_index(rows), all_board_member_names(rows), rows

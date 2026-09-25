"""De poort op het codepatroon (CR-12 §B9.3) — elf controles, elk rood te krijgen.

Eén vaste vorm voor elk vast vocabularium: een codetabel, een labeltabel per
taal, en een gewone `Enum` waar Python op de waarde vertakt. Deze poort is wat
die vorm afdwingt voor werk dat nog geschreven moet worden — zonder haar is de
regel een afspraak die iedereen vergeet zodra het druk wordt.

**Twee vormen, en welke het is hangt af van de telling.** Staat er nog werk
open, dan is de controle een **ratel**: de overtreders van vandaag staan in
`tests/codes_baseline.py`, een nieuwe is rood, en een verdwenen overtreder moet
uit de lijst of de test is rood. Is de telling nul, dan is het een **harde
poort**. Fase 5 van CR-12 haalt de lijsten en de uitzonderingslogica samen weg.

**Waarom de losse-stringcontrole een AST-wandeling is en geen mypy-regel
(§B4.8).** #779 rekende op `strict_equality`. Dat werkt hier niet: de modellen
gebruiken de oude `Column()`-stijl, dus mypy typeert elk kolomattribuut als
`Any`, en `Any == "paid"` is nooit een fout. Een poort daarop zou groen staan
met alle tweeënnegentig vergelijkingen erin — precies de soort test die
`CLAUDE.md` verbiedt.

## Bewijs dat elke controle rood kán worden

Werkwijze van de css-poort (#652): één overtreding echt maken, kijken of ze
aanslaat, herstellen. Alle elf zo gemeten op 26 september 2026, elk apart, met
de overtreding die hier staat:

| Controle | Overtreding | Sloeg aan |
|---|---|---|
| FK geregistreerd | `meetings.meetings.location` aan `fk_from` toegevoegd | ja |
| FK-net (ratel) | kolom `payment_kind = Column(String(20))` op `Meeting` | ja |
| Labeldekking | de `en`-lus uit de zaai-helper gehaald | ja — `code nl heeft geen en-label` |
| Enum = codes | lid `MeetingStatus.CANCELLED` zonder rij | ja |
| Enum zonder lijst (ratel) | `class Proef(Enum)` in `meetings/models.py` | ja |
| Tonen totaal | `MeetingStatus.SENT` uit de tonenmapping | ja |
| Geen labelwoordenboeken (ratel) | `STATUS_LABELS = {...}` terug in `meetings/admin_ui.py` | ja |
| Geen templatevergelijkingen (ratel) | `{% if meeting.status == "sent" %}` in `_vg_document.html` | ja |
| Losse strings (ratel) | `meeting.status == "sent"` in `meetings/service.py` | ja |
| Enumleden Engels | lid `VERSTUURD = "verstuurd"` toegevoegd | ja — noemt het lid |
| Vorm | kolom `description` uit de labeltabel van de helper | ja |

Eén meting is twee keer gedaan en dat is het vermelden waard: bij "enumleden
Engels" hernoemde ik eerst `SENT` naar `VERSTUURD`. Daardoor viel het importeren
van `service.py` om en draaide de test niet — een groene uitkomst die niets
bewijst. De overtreding moet dus **additief** zijn: een lid erbij, niet een lid
hernoemd. Dezelfde valkuil als een gate die nergens kijkt (#678), alleen dan aan
de kant van het bewijs.
"""
import ast
import re
from pathlib import Path

import pytest
from sqlalchemy import String, inspect, text

from app.database import Base
from app.domains.registry import load_all_models
from app.kernel.codes import (
    ExternalVocabulary,
    TechnicalEnum,
    code_label,
    registry,
)
from tests import codes_baseline as basis
from tests._bestanden import bestanden

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"

#: Attribuutnamen die een vast vocabularium aanduiden. Het net van §B9.3, en
#: uitdrukkelijk niet meer dan dat: een kolom die `categorie` heet ontsnapt
#: eraan tot iemand haar registreert. De reviewregel bij een nieuwe
#: `String`-kolom met een letterlijke default blijft "is dit een lijst?".
VOCABULARIUM = {
    "status", "type", "kind", "method", "role", "mode", "state",
    "variant", "layout", "preset", "style", "audience", "provider",
    "purpose", "direction", "format", "gender", "source",
}

#: Suffixen die hetzelfde aanduiden op een kolomnaam.
VOCABULARIUM_SUFFIX = ("_status", "_type", "_kind", "_method", "_role",
                       "_code", "_mode", "_state", "_purpose", "_variant")

#: Tabellen waarop de FK-regel niet geldt: history is append-only en moet een
#: ingetrokken code overleven (§F4), en de code-/labeltabellen zijn zelf de lijst.
def _is_vrijgesteld(tabel: str) -> bool:
    return (tabel.endswith("_history") or tabel.endswith("_codes")
            or tabel.endswith("_labels") or tabel == "alembic_version")


def _is_vocabularium(kolomnaam: str) -> bool:
    return (kolomnaam in VOCABULARIUM
            or kolomnaam.endswith(VOCABULARIUM_SUFFIX))


def _pad(bestand: Path) -> str:
    return str(bestand.relative_to(BACKEND))


# ── Bronbestanden, altijd via de helper (#678) ───────────────────────────────

def _python_bestanden() -> list[Path]:
    return bestanden(APP.rglob("*.py"), wat="de Python-bestanden onder app/",
                     minstens=100)


def _template_bestanden() -> list[Path]:
    return bestanden(APP.rglob("*.html"), wat="de templates onder app/",
                     minstens=50)


# ── De verzamelaars (ook los bruikbaar om de ratel-tabel te meten) ───────────

def verzamel_enums_zonder_lijst() -> dict[str, str]:
    """`Enum`-klassen zonder `CodeList` en zonder marker → sleutel: melding."""
    load_all_models()
    in_een_lijst = {lijst.enum.__name__ for lijst in registry().values()
                    if lijst.enum is not None}
    markers = {TechnicalEnum.__name__, ExternalVocabulary.__name__}
    uit: dict[str, str] = {}
    for bestand in _python_bestanden():
        boom = ast.parse(bestand.read_text(encoding="utf-8"))
        for node in ast.walk(boom):
            if not isinstance(node, ast.ClassDef):
                continue
            basisnamen = {b.id for b in node.bases if isinstance(b, ast.Name)}
            basisnamen |= {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
            if not (basisnamen & {"Enum", "IntEnum", "StrEnum"} | (basisnamen & markers)):
                continue
            if basisnamen & markers:
                continue
            if node.name in markers:
                # De markerklassen zelf: zij zijn de uitzondering, niet een
                # geval ervan. Zonder deze regel staat de kernel op zijn
                # eigen ratel.
                continue
            if node.name in in_een_lijst:
                continue
            uit[f"{_pad(bestand)}:{node.name}"] = (
                f"{_pad(bestand)}:{node.lineno} — `{node.name}` is een Enum zonder "
                f"CodeList. Declareer er een (tabel + labels) of markeer hem als "
                f"TechnicalEnum/ExternalVocabulary met de reden.")
    return uit


def verzamel_labelwoordenboeken() -> dict[str, str]:
    """Toekenningen als `X_LABELS = {...}` in `app/` → sleutel: melding."""
    uit: dict[str, str] = {}
    for bestand in _python_bestanden():
        if bestand.name == "codes.py" and bestand.parent.name == "kernel":
            continue
        boom = ast.parse(bestand.read_text(encoding="utf-8"))
        for node in ast.walk(boom):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            for doel in node.targets:
                if not isinstance(doel, ast.Name):
                    continue
                if not re.search(r"LABELS?$", doel.id):
                    continue
                uit[f"{_pad(bestand)}:{doel.id}"] = (
                    f"{_pad(bestand)}:{node.lineno} — `{doel.id}` zet labels in "
                    f"Python. Gebruik `code_label()` en een labeltabel.")
    return uit


_TEMPLATE_VERGELIJKING = re.compile(
    r"\.(?P<attr>[a-z_]+)\s*(?P<op>==|!=)\s*(?P<quote>['\"])(?P<waarde>[^'\"]*)(?P=quote)")


def verzamel_template_vergelijkingen() -> dict[str, str]:
    """`.status == "paid"` en vrienden in een template → sleutel: melding."""
    uit: dict[str, str] = {}
    for bestand in _template_bestanden():
        for nummer, regel in enumerate(
                bestand.read_text(encoding="utf-8").splitlines(), start=1):
            for treffer in _TEMPLATE_VERGELIJKING.finditer(regel):
                attr = treffer.group("attr")
                if not _is_vocabularium(attr):
                    continue
                vergelijking = f"{attr}{treffer.group('op')}{treffer.group('waarde')}"
                uit[f"{_pad(bestand)}:{vergelijking}"] = (
                    f"{_pad(bestand)}:{nummer} — vergelijkt `{attr}` met een "
                    f"letterlijke waarde. Zet wat het scherm nodig heeft op het "
                    f"view-model (§B4.7).")
    return uit


def _string_constanten(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        uit = []
        for element in node.elts:
            uit.extend(_string_constanten(element))
        return uit
    return []


def verzamel_losse_strings() -> dict[str, str]:
    """`record.status == "paid"` in `app/**/*.py` → sleutel: melding.

    Een AST-wandeling en geen grep: een grep vindt de tekst, niet de vorm, en
    hij ziet het verschil niet tussen een vergelijking en een sleutel in een
    woordenboek.
    """
    uit: dict[str, str] = {}
    for bestand in _python_bestanden():
        if bestand.name == "codes.py" and bestand.parent.name == "kernel":
            continue
        boom = ast.parse(bestand.read_text(encoding="utf-8"))
        for node in ast.walk(boom):
            if not isinstance(node, ast.Compare):
                continue
            for operator, rechts in zip(node.ops, node.comparators):
                if not isinstance(operator, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
                    continue
                for attribuut, ander in ((node.left, rechts), (rechts, node.left)):
                    if not isinstance(attribuut, ast.Attribute):
                        continue
                    if not _is_vocabularium(attribuut.attr):
                        continue
                    for waarde in _string_constanten(ander):
                        teken = {ast.Eq: "==", ast.NotEq: "!=",
                                 ast.In: " in ", ast.NotIn: " not in "}[type(operator)]
                        vergelijking = f"{attribuut.attr}{teken}{waarde}"
                        uit[f"{_pad(bestand)}:{vergelijking}"] = (
                            f"{_pad(bestand)}:{node.lineno} — vergelijkt "
                            f"`{attribuut.attr}` met {waarde!r}. Gebruik het "
                            f"Enum-lid van de lijst.")
    return uit


def verzamel_fk_net() -> dict[str, str]:
    """Kolommen die een vocabularium lijken op te slaan zonder FK → melding."""
    load_all_models()
    geregistreerd = {kolom for lijst in registry().values() for kolom in lijst.fk_from}
    uit: dict[str, str] = {}
    for tabel in Base.metadata.tables.values():
        schema = tabel.schema or "public"
        if _is_vrijgesteld(tabel.name):
            continue
        for kolom in tabel.columns:
            if not isinstance(kolom.type, String):
                continue
            if not _is_vocabularium(kolom.name):
                continue
            sleutel = f"{schema}.{tabel.name}.{kolom.name}"
            if sleutel in geregistreerd or kolom.foreign_keys:
                continue
            uit[sleutel] = (
                f"`{sleutel}` bewaart een vocabularium maar heeft geen FK naar een "
                f"codetabel — declareer een CodeList of zet hem op de ratel met "
                f"een reden.")
    return uit


VERZAMELAARS = {
    "FK_ONTBREEKT": verzamel_fk_net,
    "ENUM_ZONDER_LIJST": verzamel_enums_zonder_lijst,
    "LABELWOORDENBOEKEN": verzamel_labelwoordenboeken,
    "TEMPLATE_VERGELIJKINGEN": verzamel_template_vergelijkingen,
    "LOSSE_STRINGS": verzamel_losse_strings,
}


def _ratel(naam: str) -> None:
    """De ene vorm van elke ratel: niets nieuws, en niets dat blijft staan."""
    gevonden = VERZAMELAARS[naam]()
    bevroren = getattr(basis, naam)
    nieuw = sorted(set(gevonden) - set(bevroren))
    verdwenen = sorted(set(bevroren) - set(gevonden))
    fouten = []
    if nieuw:
        fouten.append("Nieuwe overtredingen:\n  " + "\n  ".join(gevonden[k] for k in nieuw))
    if verdwenen:
        fouten.append(
            f"Deze staan nog in `codes_baseline.{naam}` maar bestaan niet meer:\n  "
            + "\n  ".join(verdwenen)
            + "\nHaal ze uit de lijst — een ratel die niet krimpt is geen ratel.")
    assert not fouten, "\n\n".join(fouten)


# ── 1. FK-dekking, geregistreerd (hard) ──────────────────────────────────────

def test_elke_geregistreerde_kolom_heeft_zijn_fk(db_session):
    """Wat een `CodeList` in `fk_from` belooft, staat ook echt in de databank.

    Positief en exact: de registry is de lijst, dus hier is geen heuristiek
    nodig en geen ratel — een belofte zonder FK is gewoon fout.
    """
    load_all_models()
    ontbreekt = []
    for lijst in registry().values():
        for kolom in lijst.fk_from:
            schema, tabel, kolomnaam = kolom.split(".")
            fks = inspect(db_session.bind).get_foreign_keys(tabel, schema=schema)
            raak = any(kolomnaam in fk["constrained_columns"]
                       and fk["referred_table"] == f"{lijst.name}_codes"
                       for fk in fks)
            if not raak:
                ontbreekt.append(
                    f"`{kolom}` staat in de CodeList `{lijst.name}` maar draagt geen "
                    f"FK naar `{lijst.codes_table}`")
    assert not ontbreekt, "\n".join(ontbreekt)


# ── 2. FK-dekking, niet-geregistreerd (ratel) ────────────────────────────────

def test_geen_nieuwe_vocabulariumkolom_zonder_fk():
    """Het net: een nieuwe `String`-kolom die een lijst opslaat zonder codetabel."""
    _ratel("FK_ONTBREEKT")


# ── 3. Labeldekking (hard) ───────────────────────────────────────────────────

def test_elke_actieve_code_heeft_een_label_in_beide_talen(db_session):
    """Een scherm mag nooit leeg renderen, en `en` is geen "later".

    Deze change request zaait beide talen voor elke lijst; een poort die `en`
    optioneel maakt, krijgt `en` nooit.
    """
    load_all_models()
    ontbreekt = []
    for lijst in registry().values():
        codes = db_session.execute(text(
            f"SELECT code FROM {lijst.codes_table} WHERE is_active")).scalars().all()
        assert codes, f"`{lijst.codes_table}` heeft geen enkele actieve code"
        for taal in ("nl", "en"):
            aanwezig = set(db_session.execute(text(
                f"SELECT code FROM {lijst.labels_table} "
                f"WHERE language = :taal AND value <> ''"),
                {"taal": taal}).scalars().all())
            for code in codes:
                if code not in aanwezig:
                    ontbreekt.append(
                        f"`{lijst.codes_table}`: code `{code}` heeft geen "
                        f"{taal}-label")
    assert not ontbreekt, "\n".join(ontbreekt)


# ── 4. Enum = codes (hard) ───────────────────────────────────────────────────

def test_elke_enum_dekt_precies_zijn_codes(db_session):
    """Beide richtingen, ingetrokken codes meegerekend.

    Een ingetrokken code houdt haar lid (§B4.3): zonder lid leest die rij terug
    als een kale string, en een kale string is ongelijk aan elk lid. Dat is de
    fout die niemand opmerkt.
    """
    load_all_models()
    fouten = []
    for lijst in registry().values():
        if lijst.enum is None:
            continue
        in_de_tabel = set(db_session.execute(text(
            f"SELECT code FROM {lijst.codes_table}")).scalars().all())
        in_de_enum = {lid.value for lid in lijst.enum}
        for lid in sorted(in_de_enum - in_de_tabel):
            fouten.append(f"`{lijst.enum.__name__}` heeft lid met waarde `{lid}` "
                          f"zonder rij in `{lijst.codes_table}`")
        for code in sorted(in_de_tabel - in_de_enum):
            fouten.append(f"`{lijst.codes_table}` heeft code `{code}` zonder lid in "
                          f"`{lijst.enum.__name__}` — ook een ingetrokken code houdt "
                          f"haar lid")
    assert not fouten, "\n".join(fouten)


# ── 5. Enum zonder lijst (ratel) ─────────────────────────────────────────────

def test_geen_nieuwe_enum_zonder_codelijst():
    """Elke `Enum` onder `app/` hoort in een `CodeList` of draagt zijn reden.

    De uitzondering die géén nul haalt en dat ook niet hoort: een
    `TechnicalEnum` of `ExternalVocabulary`. Die worden geteld, niet
    geplafonneerd — zie de ratel-tabel onderaan.
    """
    _ratel("ENUM_ZONDER_LIJST")


# ── 6. Tonen totaal (hard) ───────────────────────────────────────────────────

def test_elke_tonenmapping_is_totaal():
    """Een badge zonder toon valt terug op grijs, en dat merkt niemand."""
    load_all_models()
    import app.main  # noqa: F401  — laadt de UI-modules die de tonen registreren

    fouten = []
    for lijst in registry().values():
        if not lijst.tones or lijst.enum is None:
            continue
        for lid in lijst.enum:
            if lid.value not in lijst.tones:
                fouten.append(f"`{lijst.enum.__name__}.{lid.name}` heeft geen "
                              f"badge-toon in de mapping van `{lijst.name}`")
    assert not fouten, "\n".join(fouten)


# ── 7-9. De drie tekstratels ─────────────────────────────────────────────────

def test_geen_nieuw_labelwoordenboek_in_python():
    _ratel("LABELWOORDENBOEKEN")


def test_geen_nieuwe_templatevergelijking_op_een_code():
    _ratel("TEMPLATE_VERGELIJKINGEN")


def test_geen_nieuwe_losse_stringvergelijking():
    _ratel("LOSSE_STRINGS")


# ── 10. Enumleden Engels (hard) ──────────────────────────────────────────────

#: Nederlandse woorden die als enumlid voorkomen of dreigen voor te komen. Geen
#: woordenboek: een net, in de geest van #780. De waarde mág Nederlands zijn —
#: dat is opgeslagen data — de NAAM niet.
NEDERLANDSE_WOORDEN = {
    "HOOFDLID", "PARTNER", "KIND", "GEZIN", "LID", "LEDEN", "BEDRIJF",
    "VERENIGING", "FEITELIJKE", "VERSTUURD", "BETAALD", "OPENSTAAND",
    "VEREFFEND", "GEANNULEERD", "MISLUKT", "AFWACHTING", "VERSLAG",
    "OVERSCHRIJVING", "CONTANT", "LIJN", "KLEUR", "BEELD", "TEKST",
    "EENVOUDIG", "AANWEZIG", "VERONTSCHULDIGD", "BIJLAGE", "SOORT",
}


def test_enumleden_van_een_codelijst_hebben_engelse_namen():
    """De waarde is data en blijft, de naam is een identifier en is Engels.

    `RelationType.PRIMARY_MEMBER = "HOOFDLID"` — anders wordt elke Nederlandse
    code een nieuwe Nederlandse identifier en loopt de #780-ratel vol.
    """
    load_all_models()
    fouten = []
    for lijst in registry().values():
        if lijst.enum is None:
            continue
        for lid in lijst.enum:
            for woord in lid.name.split("_"):
                if woord in NEDERLANDSE_WOORDEN:
                    fouten.append(
                        f"`{lijst.enum.__name__}.{lid.name}`: ledennamen zijn Engels "
                        f"— de waarde `{lid.value}` blijft zoals ze opgeslagen is")
    assert not fouten, "\n".join(fouten)


# ── 11. Vorm (hard) ──────────────────────────────────────────────────────────

CODES_KOLOMMEN = {"code", "sort_order", "is_active", "created_at"}
LABELS_KOLOMMEN = {"code", "language", "value", "description", "created_at",
                   "updated_at"}


def test_elke_lijst_heeft_de_vorm_die_de_helper_schrijft(db_session):
    """De helper schreef ze; deze poort bewijst dat niemand ze nadien bijstelde.

    Inclusief de FK van `language` naar `mdm.language_codes`: dat is de reden
    dat er één taallijst is, en het is de enige plek waar hij per lijst
    gecontroleerd wordt (`mdm/codes.py` laat `fk_from` daarom leeg).
    """
    load_all_models()
    inspecteur = inspect(db_session.bind)
    fouten = []
    for lijst in registry().values():
        for tabel, verwacht in ((f"{lijst.name}_codes", CODES_KOLOMMEN),
                                (f"{lijst.name}_labels", LABELS_KOLOMMEN)):
            aanwezig = {k["name"] for k in
                        inspecteur.get_columns(tabel, schema=lijst.schema)}
            if aanwezig != verwacht:
                fouten.append(
                    f"`{lijst.schema}.{tabel}` heeft kolommen {sorted(aanwezig)}, "
                    f"verwacht {sorted(verwacht)}")
        taal_fk = [fk for fk in inspecteur.get_foreign_keys(
                       f"{lijst.name}_labels", schema=lijst.schema)
                   if fk["constrained_columns"] == ["language"]]
        if not taal_fk or taal_fk[0]["referred_table"] != "language_codes":
            fouten.append(
                f"`{lijst.labels_table}.language` wijst niet naar "
                f"`mdm.language_codes` — dan kan er elke spelling in staan")
    assert not fouten, "\n".join(fouten)


# ── De ratel-tabel (AC5) ─────────────────────────────────────────────────────

def _tel_mapped_enum_kolommen() -> int:
    """Kolommen geschreven als `Mapped[X] = mapped_column(EnumColumn(X))` (§B4.8).

    Via de AST en niet via een tekstzoekopdracht, en dat is hier geen smaak: de
    eerste versie telde de letterlijke tekst `mapped_column(EnumColumn` en gaf 0
    terwijl de enige zo geschreven kolom er gewoon stond — de aanroep liep over
    twee regels. Een teller die nul geeft omdat de vorm net anders staat, is
    dezelfde fout als een gate die nergens kijkt (#678), en hij is hier meteen
    opgetreden.
    """
    aantal = 0
    for bestand in _python_bestanden():
        for node in ast.walk(ast.parse(bestand.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "mapped_column"):
                continue
            for kind in ast.walk(node):
                if (isinstance(kind, ast.Call) and isinstance(kind.func, ast.Name)
                        and kind.func.id == "EnumColumn"):
                    aantal += 1
                    break
    return aantal


def ratel_tabel(db_session=None) -> list[tuple[str, int]]:
    """De getallen van §B9.2 zoals de poort ze meet, niet zoals grep ze raadde.

    **Wat hier bewust ontbreekt.** §B9.2 opent met "lijsten met een vast
    vocabularium: 49". Dat getal is een *inventaris* uit §B5.3 — iemand heeft de
    codebase gelezen en de lijsten geteld, in welke vorm ze ook stonden. Geen
    poort kan dat namaken: een lijst die vandaag een moduleconstante is of een
    kale string met een commentaar, is per definitie niet herkenbaar aan een
    vorm. Wat hier staat is de helft die wél meetbaar is: hoeveel er in het
    patroon zitten, en hoeveel er nog buiten staan per soort overtreding. De
    49 blijft de teller waar de 2 hieronder naartoe groeit, en die staat in het
    document.
    """
    load_all_models()
    lijsten = registry()
    technisch = sum(
        1 for bestand in _python_bestanden()
        for node in ast.walk(ast.parse(bestand.read_text(encoding="utf-8")))
        if isinstance(node, ast.ClassDef)
        and {b.id for b in node.bases if isinstance(b, ast.Name)}
        & {"TechnicalEnum", "ExternalVocabulary"})
    mapped = _tel_mapped_enum_kolommen()
    regels = [
        ("lijsten in het patroon (CodeList) — doel 49, zie §B5.3", len(lijsten)),
        ("… met een Enum", sum(1 for x in lijsten.values() if x.enum is not None)),
        ("enum-dragende kolommen als Mapped[]", mapped),
        ("vocabulariumkolommen zonder FK (ratel)", len(basis.FK_ONTBREEKT)),
        ("enums zonder CodeList (ratel)", len(basis.ENUM_ZONDER_LIJST)),
        ("enums gemarkeerd technisch/extern (geteld, niet geplafonneerd)", technisch),
        ("labelwoordenboeken in Python (ratel)", len(basis.LABELWOORDENBOEKEN)),
        ("templatevergelijkingen op een code (ratel)",
         len(basis.TEMPLATE_VERGELIJKINGEN)),
        ("losse stringvergelijkingen in .py (ratel)", len(basis.LOSSE_STRINGS)),
    ]
    if db_session is not None:
        for taal in ("nl", "en"):
            aantal = sum(db_session.execute(text(
                f"SELECT count(*) FROM {lijst.labels_table} WHERE language = :taal"),
                {"taal": taal}).scalar_one() for lijst in lijsten.values())
            regels.append((f"labelrijen in `{taal}`", aantal))
    return regels


def test_de_ratel_tabel_is_meetbaar_en_wordt_afgedrukt(capsys, db_session):
    """AC5: de tabel komt uit de poort, niet uit het document.

    Draai `pytest -s -k ratel_tabel` en plak de uitvoer in het afsluit-comment
    van het fase-issue. Elk getal moet lager of gelijk zijn aan dat van de
    vorige fase — dat is de hele ratel.
    """
    regels = ratel_tabel(db_session)
    with capsys.disabled():
        print("\n\n§B9.2 — gemeten door de poort\n")
        for naam, aantal in regels:
            print(f"  {aantal:>5}  {naam}")
        print()
    assert all(aantal >= 0 for _, aantal in regels)


# ── De poort kan zelf rood worden ────────────────────────────────────────────

@pytest.mark.parametrize("naam", sorted(VERZAMELAARS))
def test_elke_ratel_kijkt_ergens_naar(naam):
    """#678 in het klein: een verzamelaar die niets scant is voor altijd groen.

    De verzamelaars gebruiken `bestanden()`, dus een leeg pad valt daar al op.
    Deze test dekt het geval erna: een verzamelaar die wél bestanden leest maar
    door een gewijzigde vorm nooit meer iets herkent. Twee van de vijf horen
    vandaag treffers te hebben; dat ze bestaan is het bewijs dat de wandeling
    werkt.
    """
    gevonden = VERZAMELAARS[naam]()
    bevroren = getattr(basis, naam)
    assert set(gevonden) >= set(bevroren), (
        f"`{naam}` vindt minder dan de bevroren lijst — dat is óf opruimwerk "
        f"(haal ze uit de baseline) óf een verzamelaar die stilgevallen is")

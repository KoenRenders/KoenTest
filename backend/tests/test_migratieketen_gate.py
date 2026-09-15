"""#951: de poort op de migratieketen, en het bewijs dat ze rood kán worden.

De logica staat in `tests/_migratieketen.py`, want `conftest` roept haar aan vóór
`alembic upgrade head`. Dat is geen implementatiedetail maar de kern van dit
issue: viel de suite om op `MultipleHeads`, dan kwam een test die het netjes
uitlegt er nooit meer aan toe. De melding hoort te staan waar de schade ontstaat.

Deze tests toetsen de lezer zelf — met verzonnen migraties in een tijdelijke map,
zodat ze niets over de echte reeks hoeven aan te nemen — plus de echte reeks als
tegenproef.

## Bewijs dat elk geval rood wordt

Met de werkwijze van de css-poort (#652): overtreding maken, kijken of ze
aanslaat, herstellen. Elk van de drie is op 15 september 2026 ook één keer écht in
`alembic/versions/` gemaakt, niet alleen in een tijdelijke map:

| Overtreding | Sloeg aan | Wat de suite toonde |
|---|---|---|
| tweede bestand met `revision = "124"` | ja | eerst `CommandError: Multiple head revisions` uit de fixture — dáárom staat de controle nu vóór `command.upgrade` |
| tweede migratie onder dezelfde `down_revision` | ja | beide heads, met de jongste benoemd |
| `down_revision = "999"` | ja | het bestand en de zoekgeraakte id |

Die eerste regel is de reden dat deze poort verplaatst is naar `conftest`: als
test alléén was ze nutteloos, want ze werd overstemd door precies het probleem dat
ze moest uitleggen.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests._migratieketen import Migratie, lees_migraties, melding, problemen

ALEMBIC = Path(__file__).resolve().parents[1] / "alembic"


def _schrijf(map_: Path, naam: str, revision: str, down: str | None) -> None:
    onder = "None" if down is None else repr(down)
    (map_ / naam).write_text(
        f'"""Verzonnen migratie voor de poorttest."""\n'
        f"revision = {revision!r}\ndown_revision = {onder}\n"
        "def upgrade() -> None: pass\ndef downgrade() -> None: pass\n",
        encoding="utf-8")


@pytest.fixture
def keten(tmp_path):
    """Een geldige reeks van twintig, waar elke test één ding aan stukmaakt.

    Twintig omdat `lees_migraties` een niet-leeg-controle draagt (#678) die
    minstens twintig bestanden verwacht — een poort die nergens kijkt staat groen
    zonder iets te bewaken.
    """
    vorige: str | None = None
    for nummer in range(1, 21):
        rev = f"{nummer:03d}"
        _schrijf(tmp_path, f"{rev}_stap.py", rev, vorige)
        vorige = rev
    return tmp_path


def test_een_gezonde_keten_geeft_geen_meldingen(keten):
    """De tegenproef bij alle drie: zonder haar zou een poort die altijd weigert
    er identiek uitzien."""
    assert problemen(lees_migraties(keten)) == []


def test_twee_migraties_met_dezelfde_id(keten):
    """Het geval van 15 september: twee takken kozen hetzelfde nummer.

    **Kapotgemaakt om te toetsen:** een tweede bestand met `revision = "020"`.
    De melding moet béíde namen dragen — zonder die twee begint de reparatie met
    zoeken, en dat is precies de kostprijs die dit issue weghaalt.
    """
    _schrijf(keten, "020_andere_tak.py", "020", "019")

    fouten = problemen(lees_migraties(keten))
    tekst = "\n".join(fouten)
    assert "dezelfde revision-id" in tekst
    assert "020_stap.py" in tekst and "020_andere_tak.py" in tekst


def test_twee_heads_noemt_de_jongste(keten):
    """De vorm waarop de suite vroeger in haar geheel omviel.

    **Kapotgemaakt om te toetsen:** een tweede migratie onder `019`, dus twee
    einden. De melding moet zeggen wélke de jongste is én welke regel er moet
    veranderen: wie na de melding nog moet uitzoeken wát hij moet doen, is niet
    geholpen.
    """
    _schrijf(keten, "021_andere_tak.py", "021", "019")

    tekst = "\n".join(problemen(lees_migraties(keten)))
    assert "2 heads" in tekst
    assert "De jongste is 021_andere_tak.py" in tekst
    assert "down_revision = '020'" in tekst, (
        "de melding noemt niet welke regel er moet veranderen")


def test_twee_heads_met_hetzelfde_volgnummer_wijst_geen_jongste_aan(keten):
    """De randvorm van het echte geval: twee takken kozen hetzelfde nummer, dus
    "de jongste" bestaat niet.

    Dan is elke keuze goed zolang er één head overblijft — en dat hoort de melding
    te zeggen in plaats van een willekeurige aan te wijzen alsof het uitmaakt.
    """
    _schrijf(keten, "020_andere_tak.py", "020_bis", "019")

    tekst = "\n".join(problemen(lees_migraties(keten)))
    assert "2 heads" in tekst
    assert "geen jongste aan te wijzen" in tekst
    assert "De jongste is" not in tekst


def test_een_down_revision_die_nergens_heen_wijst(keten):
    """De stille variant: het bestand is er, de id klopt, en toch hangt de
    migratie nergens onder.

    **Kapotgemaakt om te toetsen:** `down_revision = "999"`.
    """
    _schrijf(keten, "021_zwevend.py", "021", "999")

    tekst = "\n".join(problemen(lees_migraties(keten)))
    assert "021_zwevend.py hangt onder '999'" in tekst
    assert "nergens een revision" in tekst


def test_de_melding_zegt_dat_de_suite_niet_kapot_is(keten):
    """De toon is hier onderdeel van de reparatie.

    Wie `MultipleHeads` over tweeduizend tests heen ziet, denkt dat er iets groots
    stuk is. De kop zegt daarom eerst wat het níet is.
    """
    _schrijf(keten, "021_andere_tak.py", "021", "019")
    tekst = melding(problemen(lees_migraties(keten)))
    assert "géén kapotte suite" in tekst


# ── De echte reeks ─────────────────────────────────────────────────────────

def test_de_echte_keten_klopt():
    """Dezelfde controle die `conftest` draait, als gewone test.

    Ze staat hier dubbel en dat is met opzet: `conftest` stopt de hele run en is
    daarmee onzichtbaar in de uitslag. Een test die faalt, staat in het lijstje.
    """
    fouten = problemen()
    assert not fouten, melding(fouten)


def test_de_bestaande_gemengde_nummering_is_onschadelijk():
    """Bestaande migraties worden **niet** hernoemd, en dat is een beslissing.

    Alembic geeft niets om bestandsnamen, dus een reeks met `001` naast
    `126_2026_09_15_…` loopt gewoon. Een grote hernoeming zou elke openstaande tak
    breken en niets opleveren.
    """
    migraties = lees_migraties()
    assert all(m.revision for m in migraties), (
        "elke migratie hoort een revision-id te hebben")
    beginpunten = [m.naam for m in migraties if m.down_revision is None]
    assert len(beginpunten) == 1, f"verwacht één beginpunt, gevonden: {beginpunten}"


# ── De generator van een nieuwe id ─────────────────────────────────────────

def _generator():
    """De twee functies uit `env.py`, los uitgevoerd.

    `env.py` draait bij import meteen migraties, dus alleen deze twee definities
    worden eruit gesneden. Ze uit de echte bron halen en niet nabouwen: anders
    toetst deze test een kopie en blijft ze groen als `env.py` verandert.
    """
    pad = ALEMBIC / "env.py"
    boom = ast.parse(pad.read_text(encoding="utf-8"))
    stukken = [node for node in boom.body
               if isinstance(node, ast.FunctionDef)
               and node.name in ("_volgende_volgnummer", "_nieuwe_id")]
    assert len(stukken) == 2, "de id-generator van #951 staat niet meer in env.py"
    ruimte: dict = {"__file__": str(pad)}
    exec(compile(ast.Module(body=stukken, type_ignores=[]), str(pad), "exec"), ruimte)
    return ruimte


def test_een_nieuwe_migratie_krijgt_een_tijdstempel_in_haar_id():
    """De conventie wordt gegenereerd, niet onthouden.

    Een tijdstempel tot op de seconde kan niet botsen tussen twee CLI's; het
    volgnummer ervoor houdt de map leesbaar en sorteerbaar.
    """
    class _Directief:
        rev_id = "wordt overschreven"

    directief = _Directief()
    _generator()["_nieuwe_id"](None, None, [directief])

    assert re.fullmatch(r"\d{3}_\d{4}_\d{2}_\d{2}_\d{6}", directief.rev_id), (
        f"een nieuwe id hoort <volgnummer>_<tijdstempel> te zijn, kreeg "
        f"{directief.rev_id!r}")
    nummers = [m.volgnummer for m in lees_migraties()]
    assert int(directief.rev_id.split("_")[0]) == max(nummers) + 1, (
        "het volgnummer loopt niet door op wat er staat — dan sorteert de map niet")


def test_de_generator_laat_een_directive_zonder_id_met_rust():
    """`alembic revision --rev-id=iets` moet blijven werken.

    De hook draait op élke aanmaak. Zou hij een meegegeven id overschrijven, dan
    is dat precies op het moment dat iemand bewust een id kiest — bij het
    repareren van een botsing.
    """
    class _ZonderId:
        rev_id = None

    directief = _ZonderId()
    _generator()["_nieuwe_id"](None, None, [directief])
    assert directief.rev_id is None


def test_alembic_roept_de_generator_ook_echt_aan(tmp_path):
    """De bedrading, niet de functie — en dít is waar het bijna misging.

    `alembic revision` draait `env.py` **niet** tenzij `revision_environment`
    aanstaat in `alembic.ini`. Zonder die regel wordt
    `process_revision_directives` nooit aangeroepen en krijgt een nieuwe migratie
    gewoon de standaard-uuid: de eerste droogloop leverde
    `283f93eac489_proef_nieuwe_id.py` op terwijl de test hierboven groen stond.

    De functie werkte. Niemand riep haar aan. Dat is dezelfde vorm als de
    veertien gates uit #678 en als het contactblok van #945: een test die het
    onderwerp rechtstreeks aanroept, blijft groen als het nergens meer
    aangesloten is.

    Deze test roept daarom alembic aan en kijkt naar het bestand dat eruit komt.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(ALEMBIC))
    # Een eigen, lege versiemap: deze test hoort niets aan de echte reeks toe te
    # voegen. Het volgnummer komt wél uit de echte map — dat is de bedoeling.
    cfg.set_main_option("version_locations", str(tmp_path))

    command.revision(cfg, message="poorttest")

    gemaakt = list(tmp_path.glob("*.py"))
    assert len(gemaakt) == 1, f"verwacht één nieuw bestand, kreeg {gemaakt}"
    naam = gemaakt[0].name
    assert re.match(r"\d{3}_\d{4}_\d{2}_\d{2}_\d{6}_", naam), (
        f"alembic gebruikte de generator niet — bestandsnaam is {naam!r}. "
        "Staat `revision_environment = true` nog in alembic.ini?")
    gemaakt_rev = Migratie(gemaakt[0]).revision
    assert re.fullmatch(r"\d{3}_\d{4}_\d{2}_\d{2}_\d{6}", gemaakt_rev)


def test_revision_environment_staat_aan():
    """De ene regel waar de vorige test op staat of valt.

    Ze staat er apart bij zodat de melding de oorzaak noemt in plaats van alleen
    het gevolg: een bestandsnaam die niet klopt, stuurt je naar de generator
    terwijl het probleem in de ini staat.
    """
    ini = (ALEMBIC.parent / "alembic.ini").read_text(encoding="utf-8")
    assert re.search(r"^revision_environment\s*=\s*true", ini, re.MULTILINE), (
        "zonder `revision_environment = true` draait env.py niet bij "
        "`alembic revision`, en dan is de id-generator van #951 dood gewicht")


def test_het_sjabloon_bestaat_en_zet_de_id_niet_zelf():
    """Zonder `script.py.mako` schrijft iedereen zijn migratie met de hand, en dan
    is elke conventie een geheugenkwestie.

    Het sjabloon moet de id uit alembic overnemen (`${repr(up_revision)}`) en hem
    niet zelf verzinnen — anders zijn er twee plekken die de vorm bepalen.
    """
    mako = (ALEMBIC / "script.py.mako").read_text(encoding="utf-8")
    assert "revision = ${repr(up_revision)}" in mako
    assert "down_revision = ${repr(down_revision)}" in mako

"""#1018 — wat de code uit de omgeving leest, moet er ook in kunnen komen.

De poort van #821/#917 kijkt de andere kant op: van wat **gedocumenteerd** is
naar wat doorgegeven wordt. Staat een naam in geen enkel voorbeeldbestand en is
hij geen `Settings`-veld, dan ziet ze niets.

Dat is op 19 september 2026 gebeurd (#1015): vijf variabelen van de Design
Studio werden rechtstreeks met `os.environ.get` gelezen, stonden nergens
beschreven en in geen enkel compose-bestand. De backend heeft **geen
`env_file:`**, dus ze zouden de container nooit bereiken — de kill switch stond
permanent uit en was niet aan te zetten. CI was groen.

Deze poort gaat dus van de andere kant: **gelezen → doorgegeven én beschreven.**

Twee regels, en ze vangen niet hetzelfde:

1. de naam staat in het `environment:`-blok van de backend, in élk
   compose-bestand dat de backend draait — anders komt hij niet binnen;
2. de naam staat in minstens één `.env.<env>.example` — anders weet niemand dat
   hij bestaat, ook niet wie de server beheert. **Eén** bestand volstaat: een
   variabele hoort niet overal thuis (`PLATFORM_HOSTS` staat alleen bij prod,
   gemeten), maar nergens beschreven staan is wat #1015 liet gebeuren.

Vandaag leest niets onder `app/` rechtstreeks uit de omgeving — alles loopt via
`Settings`, en dat is de bedoeling. Deze poort staat er dus voor het volgende
geval, en haar zelftest hieronder bewijst dat ze kan zien; zonder die zelftest
zou ze groen staan zonder iets te bewaken (#678).

**Gelezen uit de syntaxboom en niet met een zoekopdracht**, want dit patroon
mist een zoekopdracht:

    ENV_KEY = "BFL_API_KEY"
    ...
    os.environ.get(ENV_KEY)

Precies zo stond het in de Design Studio.

Kapotgemaakt om te controleren dat deze poort rood kan worden (gemeten):

* `os.environ.get("IETS_NIEUWS")` in een module onder `app/` → alle vijf de
  regels rood, met de naam en het bestand erbij;
* hetzelfde **via een constante** → even goed rood; dat is het geval dat een
  zoekopdracht op tekst mist;
* een module die `PLATFORM_HOSTS` leest én die naam uit
  `docker-compose.hdev.yml` gehaald → rood voor hdev, met dat bestand bij naam.

**Wat deze poort op haar eerste dag ving.** Bij het binnenhalen van master stond
er `INKSCAPE = os.environ.get("INKSCAPE_BIN", "inkscape")` in
`designstudio/render.py`: in geen compose-bestand, in geen voorbeeldbestand. Het
pad naar Inkscape was dus op geen enkele omgeving in te stellen — zit de binary
elders, dan faalt elke render en is er geen knop om dat recht te zetten. De
uitkomst was niet "zet hem op de uitzonderingslijst" en ook niet "maak er een
instelling van", maar: de knop verdween (Koen, 19 september 2026 — de binary zit
in het image, niemand hoeft ernaast te wijzen). Dat staat hier omdat een poort
met een echte vangst in haar geschiedenis minder snel wordt uitgezet omdat ze
zeurt.

Bij de meting hierboven viel ook op dat `docker-compose.dev.yml` `PLATFORM_HOSTS`
helemaal niet doorgeeft. Vandaag heeft dat geen gevolg — niets leest hem via de
omgeving, `Settings` valt terug op zijn standaard — maar het is dezelfde vorm
als #821. Gemeld, niet hier gerepareerd.
"""
import ast
from pathlib import Path

import pytest
import yaml

from tests._bestanden import bestanden

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
ENVIRONMENTS = ("dev", "hdev", "uat", "prod")

# Namen die bewust niet uit compose komen, met de reden per regel. Deze lijst mag
# alleen KRIMPEN: een lijst die groeit maakt de poort dood.
UITZONDERINGEN: dict[str, str] = {
    # Door het besturingssysteem gezet, niet door ons.
    "PATH": "staat in elke container; niets van ons",
    "HOME": "idem",
    "TZ": "zet de basis-image zelf",
    # Door de testomgeving gezet (CI, pytest, de e2e-scripts).
    "PYTEST_CURRENT_TEST": "pytest zet dit per test",
    "TEST_DATABASE_URL": "alleen de testomgeving; de container draait er niet op",
    "E2E_BASE_URL": "alleen de e2e-scripts",
    "E2E_ADMIN_EMAIL": "alleen de e2e-scripts",
    "E2E_CHROMIUM_PATH": "alleen de e2e-scripts",
    "E2E_SEEDED": "alleen de e2e-scripts",
}

# Aanroepen die een omgevingsvariabele lezen, met de plaats van de naam erin.
_LEZERS = {"getenv": 0, "get": 0}


def _modules() -> list[Path]:
    return bestanden(APP.rglob("*.py"), wat="alle Python-modules onder app/",
                     minstens=100)


def _constanten(boom: ast.AST) -> dict[str, str]:
    """Modulebrede `NAAM = "TEKST"`, zodat een naam via een constante meetelt."""
    namen = {}
    for node in ast.walk(boom):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            for doel in node.targets:
                if isinstance(doel, ast.Name):
                    namen[doel.id] = node.value.value
    return namen


def _naam_van(node: ast.AST, constanten: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constanten.get(node.id)
    return None


def _is_environ(node: ast.AST) -> bool:
    """`os.environ`, `environ`, of `os.environ` onder een andere alias."""
    if isinstance(node, ast.Attribute):
        return node.attr == "environ"
    return isinstance(node, ast.Name) and node.id == "environ"


def gelezen_namen(bron: str) -> set[str]:
    """De omgevingsvariabelen die deze broncode uitleest.

    Als losse functie zodat de zelftest hieronder haar met een voorbeeld kan
    voeden: een poort die nergens kijkt, staat groen zonder iets te bewaken.
    """
    boom = ast.parse(bron)
    constanten = _constanten(boom)
    gevonden: set[str] = set()
    for node in ast.walk(boom):
        # os.environ["X"] / environ["X"]
        if isinstance(node, ast.Subscript) and _is_environ(node.value):
            naam = _naam_van(node.slice, constanten)
            if naam:
                gevonden.add(naam)
        if not isinstance(node, ast.Call):
            continue
        functie = node.func
        if not isinstance(functie, ast.Attribute) or functie.attr not in _LEZERS:
            continue
        # os.getenv("X") / os.environ.get("X")
        is_getenv = functie.attr == "getenv"
        if not (is_getenv or _is_environ(functie.value)):
            continue
        if is_getenv and not (isinstance(functie.value, ast.Name)
                              and functie.value.id in ("os",)):
            continue
        if node.args:
            naam = _naam_van(node.args[0], constanten)
            if naam:
                gevonden.add(naam)
    return gevonden


def _gelezen_in_app() -> dict[str, str]:
    """Naam → het eerste bestand dat hem leest."""
    gevonden: dict[str, str] = {}
    for pad in _modules():
        for naam in gelezen_namen(pad.read_text(encoding="utf-8")):
            gevonden.setdefault(naam, str(pad.relative_to(APP)))
    return {n: p for n, p in gevonden.items() if n not in UITZONDERINGEN}


def _backend_environment(environment: str) -> set[str]:
    config = yaml.safe_load((ROOT / f"docker-compose.{environment}.yml").read_text())
    block = config["services"]["backend"]["environment"]
    return set(block) if isinstance(block, dict) else {r.split("=", 1)[0] for r in block}


def _documented(environment: str) -> set[str]:
    import re

    tekst = (ROOT / f".env.{environment}.example").read_text()
    # Ook becommentarieerd: zo worden optionele instellingen hier geschreven, en
    # die regel is documentatie (#917).
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", tekst, re.M))


# ── De zelftest: kan deze poort wel zien? ────────────────────────────────────

VOORBEELD = '''
import os
from os import environ

ENV_KEY = "VIA_EEN_CONSTANTE"

rechtstreeks = os.environ.get("RECHTSTREEKS", "")
haakjes = os.environ["MET_HAAKJES"]
getenv = os.getenv("VIA_GETENV")
via_constante = os.environ.get(ENV_KEY)
losse_import = environ.get("LOSSE_IMPORT")
geen_env = {"nep": 1}.get("NIET_MEETELLEN")
'''


def test_de_poort_ziet_alle_vier_de_vormen():
    """Zonder deze test bewaakt de poort misschien niets (#678).

    De vorm die ertoe doet is `VIA_EEN_CONSTANTE`: precies die miste een
    zoekopdracht op tekst, en precies zo stond het in #1015.
    """
    gezien = gelezen_namen(VOORBEELD)

    assert gezien == {"RECHTSTREEKS", "MET_HAAKJES", "VIA_GETENV",
                      "VIA_EEN_CONSTANTE", "LOSSE_IMPORT"}, gezien


# ── De regel ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_wat_de_code_leest_komt_de_container_binnen(environment):
    doorgegeven = _backend_environment(environment)

    ontbreekt = sorted(
        f"{naam} (gelezen in {pad})"
        for naam, pad in _gelezen_in_app().items() if naam not in doorgegeven)

    assert not ontbreekt, (
        f"de backend leest deze variabelen, maar docker-compose.{environment}.yml "
        f"geeft ze niet door — de backend heeft geen env_file, dus ze bereiken de "
        f"container nooit: {ontbreekt}")


def test_wat_de_code_leest_staat_ergens_beschreven():
    """In minstens één voorbeeldbestand.

    Niet in alle vier: `PLATFORM_HOSTS` staat alleen bij prod en dat is terecht —
    gemeten toen deze poort het wél eiste. Wat de regel moet vangen is de
    variabele die NERGENS staat, want die kent alleen wie de code schreef.
    """
    beschreven = set().union(*(_documented(env) for env in ENVIRONMENTS))

    ontbreekt = sorted(
        f"{naam} (gelezen in {pad})"
        for naam, pad in _gelezen_in_app().items() if naam not in beschreven)

    assert not ontbreekt, (
        "deze variabelen worden gelezen maar staan in geen enkel "
        f".env.*.example — dan weet niemand dat ze bestaan, ook niet wie de "
        f"server beheert: {ontbreekt}")


def test_de_uitzonderingen_dragen_elk_een_reden():
    zonder_reden = sorted(n for n, reden in UITZONDERINGEN.items() if not reden.strip())
    assert not zonder_reden, (
        f"een uitzondering zonder reden is een gat, geen uitzondering: {zonder_reden}")

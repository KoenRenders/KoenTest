"""#821 — een instelling die je per omgeving zet, moet de container ook bereiken.

De backend-service heeft **geen `env_file:`**: elke variabele staat expliciet in het
`environment:`-blok van de compose-bestanden. Wat daar niet staat, komt er nooit in —
hoe netjes het ook in `.env.<env>` staat.

Dat is drie keer misgegaan, elke keer met een andere naam en elke keer stil:

| # | Variabele | Gevolg |
|---|---|---|
| #798 | `SEED_OPERATOR_EMAILS` | migratie 087 kende **nul** gebruikers OPERATOR toe |
| #821 | `PLATFORM_HOSTS` | de tenant-cookie werd gezet en nooit gelezen; je wisselde ongemerkt van afdeling |
| #821 | `TENANT_HOSTNAMES` | (nog) geen gevolg — geen tenant op een eigen hostnaam |

De gate uit #798 keek naar `SEED_`-namen in migraties en dekte de andere twee niet.
Deze is algemener, en vooral: hij is **afgeleid** in plaats van opgesomd.

**De afleiding.** Een naam die in `.env.<env>.example` staat, is per definitie iets
wat je per omgeving zet — dat bestand is de lijst die iemand naast zijn server legt.
Staat diezelfde naam ook als veld op `Settings`, dan leest de BACKEND hem, en dan
hoort hij in het `environment:`-blok van de backend-service. Is hij geen
Settings-veld (`DB_PASSWORD`, `UMAMI_APP_SECRET`), dan hoort hij bij een andere
service en volstaat het dat het compose-bestand hem kent.

Zo hoeft niemand een lijst bij te werken: documenteer je een variabele voor een
omgeving, dan eist deze poort dat ze ook echt aankomt.

Kapotgemaakt om te controleren dat deze test rood kan worden: `PLATFORM_HOSTS` uit
`docker-compose.prod.yml` gehaald → rood, mét de variabele en het bestand.
"""
import ast
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "backend" / "app" / "config.py"
OMGEVINGEN = ("hdev", "uat", "prod")


def _settings_velden() -> set[str]:
    """De veldnamen van `Settings`, als OMGEVINGSNAAM (pydantic leest hoofdletters)."""
    boom = ast.parse(CONFIG.read_text())
    klasse = next((n for n in ast.walk(boom)
                   if isinstance(n, ast.ClassDef) and n.name == "Settings"), None)
    assert klasse is not None, "class Settings niet gevonden in config.py"
    velden = {n.target.id.upper() for n in klasse.body
              if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    assert len(velden) > 30, f"maar {len(velden)} instellingen gevonden — leest deze gate config.py nog?"
    return velden


def _gedocumenteerd(omgeving: str) -> set[str]:
    pad = ROOT / f".env.{omgeving}.example"
    assert pad.exists(), f"{pad.name} ontbreekt"
    namen = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", pad.read_text(), re.M))
    assert namen, f"{pad.name} documenteert geen enkele variabele"
    return namen


def _backend_omgeving(omgeving: str) -> set[str]:
    config = yaml.safe_load((ROOT / f"docker-compose.{omgeving}.yml").read_text())
    blok = config["services"]["backend"]["environment"]
    return set(blok) if isinstance(blok, dict) else {r.split("=", 1)[0] for r in blok}


@pytest.mark.parametrize("omgeving", OMGEVINGEN)
def test_elke_gedocumenteerde_backendinstelling_wordt_doorgegeven(omgeving):
    velden = _settings_velden()
    doorgegeven = _backend_omgeving(omgeving)

    ontbreekt = sorted(naam for naam in _gedocumenteerd(omgeving)
                       if naam in velden and naam not in doorgegeven)

    assert not ontbreekt, (
        f"deze instellingen staan in .env.{omgeving}.example en worden door de "
        f"backend gelezen, maar docker-compose.{omgeving}.yml geeft ze niet door — "
        f"dus ze bereiken de container nooit: {ontbreekt}")


@pytest.mark.parametrize("omgeving", OMGEVINGEN)
def test_een_gedocumenteerde_niet_backendvariabele_wordt_ergens_gebruikt(omgeving):
    """De tegenhanger, en zonder haar zou de vorige test te smal zijn.

    `DB_PASSWORD` en `UMAMI_APP_SECRET` zijn geen `Settings`-velden — die horen bij
    de db- en umami-service. Ze moeten dus niet in het backend-blok staan, maar wél
    ergens door het compose-bestand gebruikt worden. Een naam die je documenteert en
    nergens leest, is óók een stille belofte.
    """
    velden = _settings_velden()
    inhoud = (ROOT / f"docker-compose.{omgeving}.yml").read_text()

    ongebruikt = sorted(naam for naam in _gedocumenteerd(omgeving)
                        if naam not in velden and naam not in inhoud)

    assert not ongebruikt, (
        f"deze variabelen staan in .env.{omgeving}.example maar komen in "
        f"docker-compose.{omgeving}.yml niet voor: {ongebruikt}")

"""#798 — een `SEED_*` die een migratie leest, moet de container ook bereiken.

De backend-service heeft **geen `env_file:`**: elke variabele staat expliciet in het
`environment:`-blok van de compose-bestanden. Wat daar niet staat, komt de container
nooit in — hoe netjes het ook in `.env.<env>` staat.

`SEED_OPERATOR_EMAILS` stond er niet in. Migratie 087 las dus haar placeholder, vond
niemand met dat adres, en kende **nul** gebruikers de rol OPERATOR toe. Gevolg:
`/admin/tenants` was voor niemand bereikbaar en de tenant-instellingen konden na een
verse migratie niet ingevuld worden.

Gemeten bij de upgrade-generale voor v2.0.0, op een teruggezette PROD-dump: 26
migraties zonder fouten, alle rijen intact — en **OPERATORs: 0**, terwijl het adres
uit `SEED_OPERATOR_EMAILS` wél als gebruiker in die databank bestond. Dat laatste is
het bewijs: het adres klopte, de gebruiker bestond, en de variabele kwam er niet in.

**De valkuil uit #678 staat hieronder als eerste assertie.** Vindt deze test geen
enkele `SEED_`-variabele, dan bewaakt ze niets en hoort ze te falen in plaats van
groen te staan — een verplaatste map of een gewijzigde leeswijze maakt zo'n gate
anders voorgoed groen.

Kapotgemaakt om te controleren dat deze test rood kan worden: `SEED_OPERATOR_EMAILS`
uit `docker-compose.uat.yml` gehaald → de test valt om en noemt bestand én variabele.
"""
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
MIGRATIES = ROOT / "backend" / "alembic" / "versions"
COMPOSE = ["docker-compose.hdev.yml", "docker-compose.uat.yml",
           "docker-compose.prod.yml"]


def _gelezen_door_migraties() -> set[str]:
    bestanden = list(MIGRATIES.glob("*.py"))
    assert len(bestanden) > 50, (
        f"maar {len(bestanden)} migraties gevonden — kijkt deze test wel in de "
        "juiste map?")
    namen: set[str] = set()
    for pad in bestanden:
        # Elke SEED_-naam als tekenreeks, en NIET alleen die binnen `os.getenv(...)`.
        # Die engere vorm miste precies de variabele waar dit issue over gaat:
        # migratie 087 leest haar via een eigen `_emails(var, default)`-helper, dus
        # de naam staat daar als argument en niet in een `getenv`-aanroep. Gemeten:
        # met de enge regex bleef deze gate groen terwijl SEED_OPERATOR_EMAILS uit
        # een compose-bestand verwijderd was — de fout die #798 beschrijft.
        namen |= set(re.findall(r'["\'](SEED_[A-Z_]+)["\']', pad.read_text()))
    return namen


def _doorgegeven_aan_de_backend(bestand: str) -> set[str]:
    """De sleutels uit het `environment:`-blok van de backend-service.

    Bewust de YAML parsen en niet het hele bestand doorzoeken: een `SEED_`-naam in
    een commentaarregel of bij een andere service zou een substring-test tevreden
    stellen terwijl de backend haar nooit ziet.
    """
    config = yaml.safe_load((ROOT / bestand).read_text())
    omgeving = config["services"]["backend"]["environment"]
    return set(omgeving) if isinstance(omgeving, dict) else {
        r.split("=", 1)[0] for r in omgeving}


def test_elke_seed_variabele_bereikt_de_backend():
    gelezen = _gelezen_door_migraties()

    assert gelezen, (
        "geen enkele SEED_-variabele gevonden in de migraties — deze gate kijkt "
        "nergens en zou dus voorgoed groen staan (#678)")

    ontbreekt = {}
    for bestand in COMPOSE:
        mist = sorted(gelezen - _doorgegeven_aan_de_backend(bestand))
        if mist:
            ontbreekt[bestand] = mist
    assert not ontbreekt, (
        "deze variabelen worden door een migratie gelezen maar niet aan de backend "
        f"doorgegeven, dus ze bereiken de container nooit: {ontbreekt}")


def test_de_drie_omgevingen_geven_dezelfde_seeds_door():
    """Anders werkt een rol-seed op HDEV en niet op PROD, en dat merk je pas daar."""
    per_bestand = {b: _doorgegeven_aan_de_backend(b) & _gelezen_door_migraties()
                   for b in COMPOSE}
    waarden = list(per_bestand.values())

    assert all(v == waarden[0] for v in waarden), (
        f"de omgevingen geven verschillende SEED_-variabelen door: {per_bestand}")

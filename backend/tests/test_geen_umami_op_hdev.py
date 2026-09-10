"""#820 — HDEV heeft geen Umami, en dat is een beslissing.

Gemeten op 10 september 2026: de instance op HDEV had zijn laatste bezoek op
**13 juli 2026** geregistreerd en gebruikte 155,9 MiB. Dat 13 juli precies de dag is
waarop HDEV server-rendered werd, is geen toeval: het trackingscript verdween bij de
React-exit (#405) en is met #808 alleen teruggekomen voor omgevingen mét
tenant-instellingen. HDEV heeft die bewust niet, zodat testverkeer nooit in de
productiecijfers kan belanden.

Er werd dus niet alleen niets gemeten — er *zal* ook niets gemeten worden. Koen,
10 september 2026: *"we gaan hem nooit gebruiken."*

**Waarom hier een test en niet alleen een commit.** Een verwijderde service komt terug
zodra iemand een compose-bestand kopieert van een omgeving waar hij wél hoort. Deze
test zegt niet "Umami is slecht" maar "op HDEV meet hij niets", en de tweede test zegt
er meteen bij waar hij wél hoort. Zonder die tweede zou "overal weggehaald" evengoed
groen staan, en dat is een heel andere — foute — uitkomst. Dit is uitdrukkelijk geen
consolidatie: die is met #259 afgewezen, UAT en PROD houden elk hun eigen instance.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: de service
teruggezet in `docker-compose.hdev.yml` → de eerste valt om; de service uit
`docker-compose.uat.yml` gehaald → de tweede valt om.
"""
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]


def _stack(omgeving: str) -> dict:
    pad = ROOT / f"docker-compose.{omgeving}.yml"
    assert pad.exists(), f"{pad.name} bestaat niet — deze test bewaakt niets (#678)"
    return yaml.safe_load(pad.read_text())


def test_hdev_draait_geen_umami():
    config = _stack("hdev")

    assert "umami" not in config["services"], (
        "de umami-service staat weer in de HDEV-stack; hij meet daar niets zolang "
        "HDEV geen tenant-instellingen heeft (#808)")
    poorten = [p for dienst in config["services"].values()
               for p in (dienst.get("ports") or [])]
    assert not [p for p in poorten if str(p).startswith("8082")], (
        "poort 8082 is weer gepubliceerd op HDEV")


@pytest.mark.parametrize("omgeving", ["uat", "prod"])
def test_uat_en_prod_houden_hun_eigen_umami(omgeving):
    """De tegenproef. #259 (samenvoegen tot één instance) is bewust afgewezen."""
    diensten = _stack(omgeving)["services"]

    assert "umami" in diensten, (
        f"{omgeving} heeft geen umami-service meer; #820 gaat over HDEV en alleen "
        f"over HDEV")
    assert f"umami_{omgeving}" in str(diensten["umami"]), (
        f"{omgeving} wijst niet naar zijn eigen databank umami_{omgeving}")


def test_de_hdev_omgevingsvoorbeeld_vraagt_geen_umami_secret():
    """Een secret voor een dienst die niet draait, is een secret te veel."""
    voorbeeld = (ROOT / ".env.hdev.example").read_text()

    for regel in voorbeeld.splitlines():
        kaal = regel.strip()
        if kaal.startswith("#") or "=" not in kaal:
            continue
        assert not kaal.startswith("UMAMI"), f"{kaal.split('=')[0]} staat er nog in"

"""#766 — het applicatielog overleeft een deploy.

Containerlogs horen bij de **container**, en `up --build` maakt een nieuwe. Voor een
deploy-log is dat precies goed; voor het applicatielog niet, want dat gaat over wat de
app doet en dat houdt niet op bij een deploy. Gevolg vandaag: elke vraag van de vorm
*"gebeurt dit eigenlijk?"* is alleen te beantwoorden over de periode sinds de laatste
deploy, en die is meestal kort. Bij #763 bleek dat concreet: een mislukte betaalaanmaak
laat geen spoor na, en een logregel lost dat pas op als die regel de volgende deploy
haalt.

**De gate hieronder is afgeleid, niet opgesomd.** Hij loopt over de compose-bestanden
die er zijn en eist van élk backend-blok een volume dat de container overleeft. Een
lijstje van drie namen zou blind zijn voor een vierde omgeving — precies de vorm die
in #798 en #821 drie keer misging: keurig in `.env`, nooit in de container.

Een **named volume** en geen bind-mount: de container draait als `app` (uid 10001) en
een bind-mount naar een map die Docker als root aanmaakt is voor hem niet schrijfbaar.
Een named volume neemt eigendom en rechten over van `/var/log/raak` in het image.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: het volume uit
`docker-compose.uat.yml` gehaald → de gate valt om met die omgeving erbij; de
`FileHandler` uit `configure_logging` gehaald → de gedragstest valt om.
"""
import logging
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
LOGMAP = "/var/log/raak"
# De omgevingen die volgens het issue meemoeten. Wordt hieronder afgeleid uit de
# bestanden op schijf; deze lijst is enkel de ondergrens, zodat de test faalt als
# hij níéts vindt (#678).
MINSTENS = {"hdev", "uat", "prod"}


def _compose_bestanden() -> dict[str, dict]:
    gevonden = {}
    for pad in sorted(ROOT.glob("docker-compose.*.yml")):
        omgeving = pad.name.removeprefix("docker-compose.").removesuffix(".yml")
        config = yaml.safe_load(pad.read_text())
        if "backend" in (config.get("services") or {}):
            gevonden[omgeving] = config
    return gevonden


def test_de_gate_vindt_de_omgevingen_die_hij_moet_bewaken():
    """#678: veertien gates haalden hun bestanden zonder te controleren dát ze er
    vonden. Een verplaatst bestand of een gewijzigde glob maakt zo'n gate voorgoed
    groen."""
    assert MINSTENS <= set(_compose_bestanden()), (
        "de compose-bestanden met een backend zijn niet gevonden — deze gate bewaakt niets")


@pytest.mark.parametrize("omgeving", sorted(MINSTENS))
def test_de_backend_bewaart_zijn_log_buiten_de_container(omgeving):
    config = _compose_bestanden()[omgeving]
    backend = config["services"]["backend"]
    mounts = backend.get("volumes") or []

    op_de_logmap = [m for m in mounts if isinstance(m, str) and m.endswith(f":{LOGMAP}")]
    assert op_de_logmap, (
        f"{omgeving}: de backend mount niets op {LOGMAP}, dus het applicatielog "
        f"verdwijnt bij de eerstvolgende `up --build`")

    bron = op_de_logmap[0].split(":")[0]
    assert not bron.startswith("."), (
        f"{omgeving}: {bron} is een bind-mount. Docker maakt zo'n map als root aan en "
        f"de backend draait als uid 10001, dus die kan er niet in schrijven — een "
        f"named volume erft de eigenaar uit het image")
    assert bron in (config.get("volumes") or {}), (
        f"{omgeving}: {bron} is nergens als volume gedeclareerd")


def test_het_image_maakt_de_map_met_de_juiste_eigenaar():
    """Een named volume erft eigendom van dít punt in het image. Ontbreekt de map,
    dan is ze root-eigendom en kan de app er niet in schrijven — de mount is er dan
    wél, en het log komt er tóch niet."""
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text()

    assert f"mkdir -p {LOGMAP}" in dockerfile and f"chown app:app {LOGMAP}" in dockerfile
    maak = dockerfile.index(f"mkdir -p {LOGMAP}")
    assert maak < dockerfile.index("USER app"), (
        "de map wordt gemaakt nádat het image naar de niet-root-gebruiker overschakelt")


def test_er_wordt_naar_het_bestand_gelogd_als_de_map_bestaat(tmp_path, monkeypatch):
    """Het gedrag zelf: een logregel komt óók op schijf terecht."""
    from app.config import settings
    from app.logging_config import configure_logging

    monkeypatch.setattr(settings, "app_log_dir", str(tmp_path))
    try:
        configure_logging()
        logging.getLogger("proef").warning("dit moet de deploy overleven")
        for handler in logging.getLogger().handlers:
            handler.flush()
        inhoud = (tmp_path / "app.log").read_text()
    finally:
        # Anders sleept de FileHandler naar tmp_path mee in de rest van de suite.
        monkeypatch.setattr(settings, "app_log_dir", "")
        configure_logging()

    assert "dit moet de deploy overleven" in inhoud
    assert "WARNING" in inhoud


def test_een_ontbrekende_map_blokkeert_de_start_niet(tmp_path, monkeypatch):
    """De tegenproef die dit veilig maakt. Lokaal en in CI is er geen volume; een
    applicatie die dáárop weigert te starten is erger dan een log dat ontbreekt."""
    from app.config import settings
    from app.logging_config import app_logbestand, configure_logging

    monkeypatch.setattr(settings, "app_log_dir", str(tmp_path / "bestaat-niet"))
    try:
        configure_logging()          # mag niet gooien
        assert app_logbestand() is None
        logging.getLogger("proef").info("gewoon naar stdout")
    finally:
        monkeypatch.setattr(settings, "app_log_dir", "")
        configure_logging()


def test_de_deploy_meldt_of_het_log_de_deploy_overleefde():
    """Het issue vraagt de controle op te nemen in de deploy-verificatie, zodat een
    latere wijziging die dit stilletjes terugdraait opvalt."""
    deploy = (ROOT / "deploy.sh").read_text()

    assert "applicatielog_regel" in deploy, "de deploy meldt het applicatielog niet"
    assert "nacontrole()" in deploy and deploy.index("nacontrole()") < deploy.index(
        "  applicatielog_regel\n"), "de melding staat buiten de na-controle"
    assert "/var/log/raak/app.log" in (ROOT / "logging.sh").read_text(), (
        "`raakctl diagnose` toont het applicatielog niet")


def test_raakctl_kan_het_log_teruglezen():
    """Een log dat de deploy overleeft maar onleesbaar is, lost niets op:
    `docker compose logs` kent alleen de huidige container."""
    raakctl = (ROOT / "raakctl").read_text()

    assert 'if [ "$svc" = app ]' in raakctl, "`raakctl logs <env> app` bestaat niet"
    assert "echo app" in raakctl, "`app` staat niet in de lijst met logbronnen"

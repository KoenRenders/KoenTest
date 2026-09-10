"""#604 — de deploy controleert zelf de migratieketen en de opstart.

Na élke deploy horen drie dingen te kloppen: precies één alembic-head, een `current`
die daaraan gelijk is, en een opstart zonder fouten. Dat gebeurde met de hand, of via
`raakctl diagnose` — een rapport zonder exit-code, dat je ápart draait ná de deploy.
De rooktest zelf ziet deze fouten niet: hij toetst dat publieke pagina's 200 geven en
dat de admin afgeschermd is. Een gesplitste keten passeert dat ongemerkt.

**Deze tests draaien het echte `deploy.sh`** in een wegwerpmap, met een neppe `docker`
die alembic-uitvoer en backend-logs teruggeeft. Een `grep` op "staat de check erin"
zou ook groen staan als ze de verkeerde omgeving bewaakt of nooit iets tegenhoudt —
precies de klasse fout die #800 opleverde.

De kern is het VERSCHIL tussen de omgevingen: de ketencheck is een poort op UAT/PROD
en rapporterend op HDEV, en de logcheck is voorlopig overal rapporterend. Een test die
alleen de gelukkige weg draait, of maar één omgeving, zou dat verschil niet zien.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `KETEN_GATE=0` voor
uat gezet → de terugroltest valt om, de hdev-test blijft groen; het opstartvenster
opgerekt tot de hele log → de scope-test valt om.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy.sh"

GEZONDE_LOG = """\
==> Running database migrations...
INFO  [alembic.runtime.migration] Running upgrade 094 -> 095
==> Seeding postal codes (if empty)...
  1234 postal codes already present, skipping.
==> Starting API server...
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
"""


def _bouw(tmp_path, *, heads="095 (head)\n", current="095 (head)\n",
          log=GEZONDE_LOG):
    """Een wegwerp-checkout met het ECHTE deploy.sh en een neppe buitenwereld."""
    werk = tmp_path / "checkout"
    (werk / "tests").mkdir(parents=True)
    shutil.copy(DEPLOY, werk / "deploy.sh")
    (werk / "deploy.sh").chmod(0o755)

    smoke_teller = tmp_path / "smoke-runs"
    (werk / "tests" / "run-all.sh").write_text(
        f'#!/bin/sh\necho x >> "{smoke_teller}"\nexit 0\n')
    (werk / "tests" / "run-all.sh").chmod(0o755)

    for naam in (".env.hdev", ".env.uat", ".env.prod"):
        (werk / naam).write_text("FRONTEND_URL=http://site.test\n")

    (tmp_path / "heads").write_text(heads)
    (tmp_path / "current").write_text(current)
    (tmp_path / "backendlog").write_text(log)

    nepbin = tmp_path / "bin"
    nepbin.mkdir()
    # De neppe container antwoordt op precies wat de na-controle vraagt. `ps -q db`
    # blijft leeg, zodat de pre-migratie-backup overgeslagen wordt.
    (nepbin / "docker").write_text(
        '#!/bin/sh\ncase "$*" in\n'
        f'  *"alembic heads"*) cat "{tmp_path}/heads" ;;\n'
        f'  *"alembic current"*) cat "{tmp_path}/current" ;;\n'
        f'  *"logs backend"*) cat "{tmp_path}/backendlog" ;;\n'
        'esac\nexit 0\n')
    (nepbin / "curl").write_text('#!/bin/sh\nexit 0\n')
    (nepbin / "git").write_text(
        '#!/bin/sh\ncase "$1" in describe) echo v0.0.0 ;; rev-parse) echo deadbee ;; esac\n'
        'exit 0\n')
    (nepbin / "sleep").write_text('#!/bin/sh\nexit 0\n')
    for f in nepbin.iterdir():
        f.chmod(0o755)

    return werk, nepbin, smoke_teller


def _draai(werk, nepbin, omgeving, tmp_path, **extra_env):
    env = dict(os.environ)
    env["PATH"] = f"{nepbin}:{env['PATH']}"
    # De re-exec na de checkout (#162) hoort niet bij wat hier getoetst wordt.
    env["DEPLOY_REEXEC"] = "1"
    env["LOG_OUT"] = str(tmp_path / "deploy.log")
    env.update(extra_env)
    args = ["bash", "./deploy.sh", omgeving] + (["v0.0.0"] if omgeving != "hdev" else [])
    return subprocess.run(args, cwd=werk, env=env, capture_output=True, text=True,
                          timeout=120)


@pytest.mark.parametrize("omgeving", ["hdev", "uat", "prod"])
def test_een_gezonde_deploy_gaat_gewoon_door(omgeving, tmp_path):
    """De tegenproef die de rest bruikbaar maakt: dit mag geen valse terugrol worden."""
    werk, nepbin, _ = _bouw(tmp_path)

    klaar = _draai(werk, nepbin, omgeving, tmp_path)

    assert klaar.returncode == 0, klaar.stdout[-3000:]
    assert "Migratieketen OK" in klaar.stdout and "Schone start OK" in klaar.stdout


def test_twee_heads_rollen_uat_terug(tmp_path):
    """Een gesplitste keten is de fout waar dit issue mee begon: hij passeert de
    rooktest ongemerkt, want de site antwoordt gewoon."""
    werk, nepbin, smoke_teller = _bouw(tmp_path, heads="095 (head)\n0a1b2c (head)\n")

    # DEPLOY_PREV_REF moet verschillen van wat er nú draait, anders is er geen doel
    # om naar terug te rollen en stopt het script meteen.
    klaar = _draai(werk, nepbin, "uat", tmp_path, DEPLOY_PREV_REF="v0.0.1")

    assert klaar.returncode != 0, "een gesplitste keten mag niet als geslaagd gelden"
    assert "2 heads" in klaar.stdout
    assert "Automatische rollback naar v0.0.1" in klaar.stdout
    assert smoke_teller.read_text().count("x") == 2, (
        "de terugrol draaide de rooktest niet opnieuw, of rolde vaker dan één keer terug")


def test_twee_heads_houden_hdev_niet_tegen(tmp_path):
    """HDEV is de integratielijn: luid melden, niets tegenhouden."""
    werk, nepbin, _ = _bouw(tmp_path, heads="095 (head)\n0a1b2c (head)\n")

    klaar = _draai(werk, nepbin, "hdev", tmp_path)

    assert klaar.returncode == 0, "HDEV mag hier niet op stukvallen"
    assert "2 heads" in klaar.stdout, "…maar het moet wél in de uitvoer staan"
    assert "rapporterend op hdev" in klaar.stdout


def test_een_achterlopende_current_faalt(tmp_path):
    """Twee heads is niet de enige vorm: een migratie die niet toegepast raakte laat
    de keten heel, maar de databank staat achter."""
    werk, nepbin, _ = _bouw(tmp_path, heads="095 (head)\n", current="094\n")

    klaar = _draai(werk, nepbin, "prod", tmp_path, DEPLOY_PREV_REF="v0.0.1")

    assert klaar.returncode != 0
    assert "niet gelijk aan" in klaar.stdout or "en niet [095]" in klaar.stdout


def test_een_traceback_bij_het_opstarten_wordt_gemeld_maar_rolt_niet_terug(tmp_path):
    """De logcheck is deze release bewust rapporterend: een valse terugrol op PROD
    door één ERROR-regel is duurder dan de melding missen."""
    stuk = GEZONDE_LOG.replace(
        "==> Starting API server...",
        "Traceback (most recent call last):\n  RuntimeError: seed mislukt\n"
        "==> Starting API server...")
    werk, nepbin, _ = _bouw(tmp_path, log=stuk)

    klaar = _draai(werk, nepbin, "prod", tmp_path, DEPLOY_PREV_REF="v0.0.1")

    assert klaar.returncode == 0, "LOG_GATE staat op 0; dit mag nog niets terugrollen"
    assert "fouten tijdens het opstarten" in klaar.stdout
    assert "RuntimeError: seed mislukt" in klaar.stdout


def test_verkeer_na_de_start_telt_niet_mee(tmp_path):
    """Het venster is strak: containerstart tot 'Uvicorn running'.

    Zonder die scope wordt élke deploy een klacht — een Mollie-webhook die 404't of
    een bezoeker met een ongeldige aanvraag in de seconden erna is geen deployfout.
    En met LOG_GATE=1 zou dat later een terugrol worden.
    """
    ruis = GEZONDE_LOG + (
        'ERROR:    Exception in ASGI application\n'
        'Traceback (most recent call last):\n  ValueError: kapotte aanvraag\n')
    werk, nepbin, _ = _bouw(tmp_path, log=ruis)

    klaar = _draai(werk, nepbin, "prod", tmp_path, DEPLOY_PREV_REF="v0.0.1")

    assert klaar.returncode == 0
    assert "Schone start OK" in klaar.stdout
    assert "kapotte aanvraag" not in klaar.stdout, (
        "verkeer ná 'Uvicorn running' valt binnen het opstartvenster")


def test_een_backend_die_nooit_start_wordt_gezien(tmp_path):
    """De fout die de rooktest écht niet kan zien als Caddy nog een oude container
    bedient: migraties gestart, maar 'Uvicorn running' komt nooit."""
    werk, nepbin, _ = _bouw(
        tmp_path, log="==> Running database migrations...\nINFO  [alembic] bezig\n")

    klaar = _draai(werk, nepbin, "hdev", tmp_path)

    assert "bereikte 'Uvicorn running' niet" in klaar.stdout

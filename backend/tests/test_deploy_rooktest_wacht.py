"""#800 — de rooktest mag pas beginnen als de site antwoordt.

De wachtlus stond BINNEN de `own`-tak van `deploy.sh` en pollde
`$SMOKE_BASE_DEFAULT`. Die is leeg op UAT en PROD, dus daar draaide ze nooit: de
rooktest vuurde meteen na `docker compose up`, de compressie-check kreeg een 502
(Caddy comprimeert een foutpagina niet), en het script rolde een gezonde deploy
terug. De bescherming zat dus op de omgeving die haar het minst nodig heeft.

Gemeten op 9 september 2026 bij het gelijkzetten van UAT met v2.0.1: `1 OK ·
1 gefaald` op de compressie, automatische terugrol, dezelfde fout op de
teruggerolde versie — en een minuut later drie keer netjes `content-encoding:
zstd`. De stack was gezond; alleen de test was te vroeg.

**Deze tests toetsen gedrag en niet de tekst van het script.** Een `grep` op "staat
de lus erin" zou ook groen staan als ze op de verkeerde plek of tegen de verkeerde
variabele draait — precies de fout die dit issue beschrijft. `deploy.sh` draait hier
dus echt, in een wegwerpmap, met een neppe `curl` die de eerste keren faalt. De
rooktest noteert bij welke poging hij aan de beurt kwam; dat getal ís de assertie.

Beide omgevingen staan in de parametrisering, en dat is de kern: `hdev` had de lus
al, `uat` niet. Een test die alleen `hdev` draait, zou de storing niet gezien hebben.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: de lus terug in de
`if [ "$CADDY" = "own" ]`-tak gezet met `$SMOKE_BASE_DEFAULT` → de uat-variant valt
om (de rooktest start bij poging 0), de hdev-variant blijft groen. Precies het
verschil dat de bug was.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy.sh"

# Zoveel mislukte curl-pogingen doet de neppe site vóór ze antwoordt.
TRAAG = 3


def _bouw(tmp_path, faal_altijd=False):
    """Een wegwerp-checkout met het ECHTE deploy.sh en neppe buitenwereld."""
    werk = tmp_path / "checkout"
    (werk / "tests").mkdir(parents=True)
    shutil.copy(DEPLOY, werk / "deploy.sh")
    (werk / "deploy.sh").chmod(0o755)

    teller = tmp_path / "curl-pogingen"
    gezien = tmp_path / "rooktest-zag"

    # De rooktest noteert bij welke curl-poging hij gedraaid heeft.
    (werk / "tests" / "run-all.sh").write_text(
        f'#!/bin/sh\ncat "{teller}" 2>/dev/null | wc -l > "{gezien}"\nexit 0\n')
    (werk / "tests" / "run-all.sh").chmod(0o755)

    for naam in (".env.hdev", ".env.uat", ".env.prod"):
        (werk / naam).write_text("FRONTEND_URL=http://site.test\n")

    nepbin = tmp_path / "bin"
    nepbin.mkdir()
    # curl: faalt de eerste TRAAG pogingen (zoals een 502 van Caddy), dan 200.
    drempel = 10**6 if faal_altijd else TRAAG
    (nepbin / "curl").write_text(
        f'#!/bin/sh\necho x >> "{teller}"\n'
        f'[ "$(wc -l < "{teller}")" -gt {drempel} ] && exit 0\nexit 1\n')
    (nepbin / "git").write_text(
        '#!/bin/sh\ncase "$1" in describe) echo v0.0.0 ;; rev-parse) echo deadbee ;; esac\n'
        'exit 0\n')
    # `docker compose ... ps -q db` moet leeg blijven: dan slaat het script de
    # pre-migratie-backup over en hoeven pg_dump/gzip niet nagebootst te worden.
    (nepbin / "docker").write_text('#!/bin/sh\nexit 0\n')
    # Een echte sleep zou deze test dertig seconden laten duren; de volgorde is wat
    # we toetsen, niet de wandklok.
    (nepbin / "sleep").write_text('#!/bin/sh\nexit 0\n')
    for f in nepbin.iterdir():
        f.chmod(0o755)

    return werk, nepbin, teller, gezien


def _draai(werk, nepbin, omgeving, tmp_path):
    env = dict(os.environ)
    env["PATH"] = f"{nepbin}:{env['PATH']}"
    # Het script re-exect zichzelf na de checkout (#162); die stap hoort niet bij
    # wat hier getoetst wordt en zou de neppe omgeving opnieuw opbouwen.
    env["DEPLOY_REEXEC"] = "1"
    env["LOG_OUT"] = str(tmp_path / "deploy.log")
    args = ["bash", "./deploy.sh", omgeving] + (["v0.0.0"] if omgeving != "hdev" else [])
    return subprocess.run(args, cwd=werk, env=env, capture_output=True, text=True,
                          timeout=120)


@pytest.mark.parametrize("omgeving", ["hdev", "uat", "prod"])
def test_de_rooktest_wacht_tot_de_site_antwoordt(omgeving, tmp_path):
    """Op ELKE omgeving, en dat is het hele punt: `hdev` had dit al, `uat`/`prod` niet."""
    werk, nepbin, teller, gezien = _bouw(tmp_path)

    klaar = _draai(werk, nepbin, omgeving, tmp_path)

    assert klaar.returncode == 0, klaar.stdout[-3000:] + klaar.stderr[-3000:]
    assert gezien.exists(), "de rooktest is helemaal niet gedraaid"
    poging = int(gezien.read_text().strip())
    assert poging > TRAAG, (
        f"de rooktest begon al bij poging {poging}, terwijl de site pas vanaf "
        f"poging {TRAAG + 1} antwoordt — hij start dus vóór de backend klaar is")


def test_een_site_die_nooit_antwoordt_blokkeert_de_deploy_niet(tmp_path):
    """De tegenproef, en zonder haar is de eerste test gevaarlijk.

    Een lus die eeuwig wacht ruilt een valse terugrol in voor een deploy die blijft
    hangen. De lus is begrensd op dertig pogingen; daarna draait de rooktest gewoon,
    faalt hij op een échte reden, en doet het script wat het hoort te doen.
    """
    werk, nepbin, teller, gezien = _bouw(tmp_path, faal_altijd=True)

    klaar = _draai(werk, nepbin, "uat", tmp_path)

    assert gezien.exists(), "de deploy is blijven hangen in de wachtlus"
    assert int(teller.read_text().count("x")) >= 30, (
        "de lus geeft te snel op; een trage backend is dan nog steeds een valse fail")
    assert klaar.returncode == 0  # onze neppe rooktest slaagt; het wachten is wat telt

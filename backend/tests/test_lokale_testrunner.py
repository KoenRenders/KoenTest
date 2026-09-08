"""#719 — de vangrail van `scripts/test-local.sh`.

Het script is gereedschap, geen productiecode, dus hier staat maar één ding —
maar dat ding verdient een test, want het faalgedrag is erger dan de fout zelf.
De pytest-suite **dropt en hermaakt het schema** van haar doeldatabank, en
`DATABASE_URL` en `TEST_DATABASE_URL` schelen één woord. Een verkeerd gezette
variabele moet dus stuiten op een weigering, niet op een lege databank.

**Waarom hier een neppe `docker` in het PATH staat.** Toetsen op "exit 2" alleen
zou ook slagen als het script eerst containers start, de databank aanmaakt en pás
daarna weigert. De invariant is niet de exitcode maar de **volgorde**: er wordt
niets aangeraakt vóór het oordeel. Deze `docker` schrijft daarom elke aanroep weg,
en de test kijkt of dat spoor leeg bleef.

De tweede test is de tegenhanger en zonder haar bewijst de eerste niets: een
vangrail die álles weigert houdt het spoor ook leeg, en dan is het script kapot in
plaats van veilig.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (lokaal gedraaid
met scripts/test-local.sh, niet beredeneerd):
  * de `case`-vangrail ná het `docker build`-blok gezet → de eerste test faalt op
    een spoor dat niet leeg is;
  * `raaktest|raaktest_*)` vervangen door `*)` (alles weigeren) → de tweede test
    faalt, want dan wordt docker nooit bereikt.

De laatste twee tests doen hetzelfde voor `e2e-local.sh` (#728). Dat script hoort
niet in CI thuis — daar is de databank altijd vers — maar de vangrail wél, want ze
beschermt een DROP DATABASE.
"""
import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SCRIPT = SCRIPTS / "test-local.sh"
E2E_SCRIPT = SCRIPTS / "e2e-local.sh"

pytestmark = pytest.mark.ui_agnostisch


def _draai(tmp_path, script=None, **omgeving):
    """Draait het script met een neppe `docker` die elke aanroep noteert."""
    spoor = tmp_path / "docker-aanroepen.txt"
    nepbin = tmp_path / "bin"
    nepbin.mkdir()
    nepdocker = nepbin / "docker"
    nepdocker.write_text(f'#!/bin/sh\necho "$@" >> "{spoor}"\nexit 0\n')
    nepdocker.chmod(0o755)

    env = dict(os.environ)
    for naam in ("TEST_DATABASE_URL", "TEST_DB_NAME", "E2E_DB_NAME"):
        env.pop(naam, None)
    env["PATH"] = f"{nepbin}:{env['PATH']}"
    env.update(omgeving)

    klaar = subprocess.run(["bash", str(script or SCRIPT)], env=env,
                           capture_output=True, text=True, timeout=60)
    return klaar, spoor


def test_een_doel_dat_geen_testdatabank_is_wordt_geweigerd(tmp_path):
    """En wel vóór er iets gestart of aangemaakt wordt."""
    klaar, spoor = _draai(tmp_path, TEST_DB_NAME="raakmillegem")

    assert klaar.returncode == 2, klaar.stderr or klaar.stdout
    assert "raakmillegem" in klaar.stderr
    assert not spoor.exists(), (
        "het script heeft docker aangeroepen vóór het weigerde:\n"
        + spoor.read_text())


def test_ook_een_volledige_url_wordt_getoetst(tmp_path):
    """`TEST_DATABASE_URL` omzeilt de afgeleide naam — en dus bijna de vangrail."""
    klaar, spoor = _draai(
        tmp_path,
        TEST_DATABASE_URL="postgresql+psycopg2://u:p@db:5432/raakmillegem_prod")

    assert klaar.returncode == 2, klaar.stderr or klaar.stdout
    assert not spoor.exists()


def test_een_echte_testdatabank_komt_er_wel_door(tmp_path):
    """De tegenhanger: alles weigeren is geen vangrail maar een kapot script."""
    klaar, spoor = _draai(tmp_path, TEST_DB_NAME="raaktest_proef")

    assert klaar.returncode != 2, klaar.stderr
    assert spoor.exists(), "het script bereikte docker niet met een geldige naam"


# ── e2e-local.sh (#728) ──────────────────────────────────────────────────────
# Dezelfde vangrail, en hier weegt ze zwaarder: dit script DROPT zijn doeldatabank
# en bouwt haar opnieuw op, terwijl test-local.sh alleen het schema hermaakt.


def test_de_e2e_runner_weigert_een_doel_dat_geen_e2e_databank_is(tmp_path):
    klaar, spoor = _draai(tmp_path, script=E2E_SCRIPT, E2E_DB_NAME="raakmillegem")

    assert klaar.returncode == 2, klaar.stderr or klaar.stdout
    assert "raakmillegem" in klaar.stderr
    assert not spoor.exists(), (
        "het script heeft docker aangeroepen vóór het weigerde:\n" + spoor.read_text())


def test_de_e2e_runner_laat_een_echte_e2e_databank_wel_door(tmp_path):
    """De tegenhanger — alles weigeren is geen vangrail maar een kapot script."""
    klaar, spoor = _draai(tmp_path, script=E2E_SCRIPT, E2E_DB_NAME="raake2e_proef")

    assert klaar.returncode != 2, klaar.stderr
    assert spoor.exists(), "het script bereikte docker niet met een geldige naam"

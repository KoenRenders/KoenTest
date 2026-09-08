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


def _draai(tmp_path, script=None, faal_op=None, **omgeving):
    """Draait het script met een neppe `docker` die elke aanroep noteert.

    `faal_op` laat die neppe docker met 1 stoppen zodra het woord in de argumenten
    staat — zo is te toetsen wát het script doet als een stap faalt, zonder die stap
    echt te draaien.
    """
    spoor = tmp_path / "docker-aanroepen.txt"
    nepbin = tmp_path / "bin"
    nepbin.mkdir()
    nepdocker = nepbin / "docker"
    val = (f'\ncase "$*" in *{faal_op}*) exit 1 ;; esac' if faal_op else "")
    nepdocker.write_text(f'#!/bin/sh\necho "$@" >> "{spoor}"{val}\nexit 0\n')
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


# ── De volledige poort (#739) ────────────────────────────────────────────────
# `test-local.sh` draaide alleen pytest en meldde bij #724 "1532 passed" terwijl CI
# omviel op mypy en op een niet-herbouwde app.css. Lokaal groen hoort hetzelfde te
# betekenen als CI groen.
#
# De css-controle staat hier BEWUST niet in een test. Ze roept `build-css.sh` echt
# aan, en die downloadt in een kale omgeving de Tailwind-binary en schrijft
# `app.css` in de werkmap — een test die het bestand onder zichzelf herschrijft is
# erger dan geen test. Die kant is met de hand bewezen en staat hieronder.
#
# Kapotgemaakt om te controleren dat de poort echt rood wordt (lokaal gedraaid, niet
# beredeneerd):
#   * `VeldFout(field.id, …)` vervangen door `VeldFout("geen getal", …)` → het script
#     stopt met exitcode 1 op `error: Argument 1 to "VeldFout" has incompatible type
#     "str"; expected "int"`, en bereikt pytest niet;
#   * `tracking-widest` toegevoegd aan een klasse in `site_base.html` → het script
#     stopt op "app.css liep niet gelijk met de templates", met het bestand zojuist
#     herbouwd zodat je het enkel hoeft te committen.


def test_de_poort_stopt_op_mypy_voordat_pytest_draait(tmp_path):
    """De volgorde is het punt: een typefout hoeft geen 1500 tests af te wachten."""
    klaar, spoor = _draai(tmp_path, faal_op="mypy", TEST_DB_NAME="raaktest_proef")

    assert klaar.returncode != 0, "een falende mypy hoort het script te stoppen"
    aanroepen = spoor.read_text()
    assert "mypy" in aanroepen, "mypy wordt niet gedraaid"
    assert "pytest" not in aanroepen, (
        "pytest is toch gedraaid nadat mypy faalde — dan is de volgorde zinloos")


def test_snel_slaat_de_poort_over_maar_is_niet_de_standaard(tmp_path):
    """De tegenhanger, en zonder haar bewijst de vorige test te weinig.

    `SNEL=1` bestaat voor wie tijdens het bouwen één bestand draait. De STANDAARD
    blijft de volle poort — dat is precies wat de vorige test vastlegt.
    """
    klaar, spoor = _draai(tmp_path, faal_op="mypy", SNEL="1",
                          TEST_DB_NAME="raaktest_proef")

    aanroepen = spoor.read_text()
    assert "mypy" not in aanroepen, "SNEL=1 draait mypy toch"
    assert "pytest" in aanroepen, "SNEL=1 draait niet eens pytest meer"
    assert klaar.returncode == 0, klaar.stderr

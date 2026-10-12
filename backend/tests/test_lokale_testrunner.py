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
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SCRIPT = SCRIPTS / "test-local.sh"
E2E_SCRIPT = SCRIPTS / "e2e-local.sh"

pytestmark = pytest.mark.ui_agnostisch


def _draai(tmp_path, script=None, faal_op=None, argumenten=(), **omgeving):
    """Draait het script met een neppe `docker` die elke aanroep noteert.

    `faal_op` laat die neppe docker met 1 stoppen zodra het woord in de argumenten
    staat — zo is te toetsen wát het script doet als een stap faalt, zonder die stap
    echt te draaien.
    """
    spoor = tmp_path / "docker-aanroepen.txt"
    nepbin = tmp_path / "bin"
    nepbin.mkdir()
    nepdocker = nepbin / "docker"
    val = f'\ncase "$*" in *{faal_op}*) exit 1 ;; esac' if faal_op else ""
    nepdocker.write_text(f'#!/bin/sh\necho "$@" >> "{spoor}"{val}\nexit 0\n')
    nepdocker.chmod(0o755)

    env = dict(os.environ)
    for naam in ("TEST_DATABASE_URL", "TEST_DB_NAME", "E2E_DB_NAME"):
        env.pop(naam, None)
    env["PATH"] = f"{nepbin}:{env['PATH']}"
    env.update(omgeving)

    klaar = subprocess.run(
        ["bash", str(script or SCRIPT), *argumenten],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return klaar, spoor


def test_een_doel_dat_geen_testdatabank_is_wordt_geweigerd(tmp_path):
    """En wel vóór er iets gestart of aangemaakt wordt."""
    klaar, spoor = _draai(tmp_path, TEST_DB_NAME="raakmillegem")

    assert klaar.returncode == 2, klaar.stderr or klaar.stdout
    assert "raakmillegem" in klaar.stderr
    assert not spoor.exists(), (
        "het script heeft docker aangeroepen vóór het weigerde:\n" + spoor.read_text()
    )


def test_ook_een_volledige_url_wordt_getoetst(tmp_path):
    """`TEST_DATABASE_URL` omzeilt de afgeleide naam — en dus bijna de vangrail."""
    klaar, spoor = _draai(
        tmp_path, TEST_DATABASE_URL="postgresql+psycopg2://u:p@db:5432/raakmillegem_prod"
    )

    assert klaar.returncode == 2, klaar.stderr or klaar.stdout
    assert not spoor.exists()


def test_een_echte_testdatabank_komt_er_wel_door(tmp_path):
    """De tegenhanger: alles weigeren is geen vangrail maar een kapot script."""
    # The copy with a stub css build (CR-29): this run passes mypy and would
    # otherwise rewrite the real app.css beside three other processes.
    klaar, spoor = _draai(
        tmp_path, script=_script_with_a_stub_css_build(tmp_path), TEST_DB_NAME="raaktest_proef"
    )

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
        "het script heeft docker aangeroepen vóór het weigerde:\n" + spoor.read_text()
    )


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
        "pytest is toch gedraaid nadat mypy faalde — dan is de volgorde zinloos"
    )


def test_snel_slaat_de_poort_over_maar_is_niet_de_standaard(tmp_path):
    """De tegenhanger, en zonder haar bewijst de vorige test te weinig.

    `SNEL=1` bestaat voor wie tijdens het bouwen één bestand draait. De STANDAARD
    blijft de volle poort — dat is precies wat de vorige test vastlegt.
    """
    klaar, spoor = _draai(tmp_path, faal_op="mypy", SNEL="1", TEST_DB_NAME="raaktest_proef")

    aanroepen = spoor.read_text()
    assert "mypy" not in aanroepen, "SNEL=1 draait mypy toch"
    assert "pytest" in aanroepen, "SNEL=1 draait niet eens pytest meer"
    assert klaar.returncode == 0, klaar.stderr


# ── What CI runs, the local run runs too (CR-29 D4) ──────────────────────────
# CI's `lint` job blocks on ruff and the local script ran none: a branch that was
# green here went red there on a line length. And CI runs pytest in four processes;
# a local run in one would be the slow half of the same gate.
#
# Broken to check that these can go red (run, not reasoned):
#   * the two ruff lines moved below mypy → the first test fails on "mypy" in the trace;
#   * `WORKERS=()` as the first line of that block → the second test fails;
#   * the `"$#" -gt 0` half of the condition removed → the third test fails for the
#     path argument;
#   * the guard's `raaktest_*` narrowed to `raaktest_proef` → the last test fails.


def _script_with_a_stub_css_build(tmp_path) -> Path:
    """A copy of the script in a checkout of its own, whose css build does nothing.

    A run that passes mypy reaches the css check, and that one calls the real
    `build-css.sh`, which rewrites `app.css` in the work folder. Several of these
    tests at once — the suite runs in four processes — would rewrite that file
    under each other and under every test that reads it.
    """
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "test-local.sh")
    # The script sources it (#1891).
    shutil.copy(SCRIPTS / "local-db-lib.sh", root / "scripts" / "local-db-lib.sh")
    stub = root / "scripts" / "build-css.sh"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    (root / "backend" / "app" / "static").mkdir(parents=True)
    (root / "backend" / "app" / "static" / "app.css").write_text("")
    for name in ("requirements.txt", "requirements-dev.txt"):
        (root / "backend" / name).write_text("")
    return root / "scripts" / "test-local.sh"


def _pytest_call(spoor) -> str:
    calls = [line for line in spoor.read_text().splitlines() if "-m pytest" in line]
    assert len(calls) == 1, f"expected one pytest call, found {len(calls)}"
    return calls[0]


def test_the_gate_stops_on_ruff_before_mypy_and_pytest(tmp_path):
    """The cheapest verdict first, as in CI: a style finding does not wait for a suite."""
    klaar, spoor = _draai(tmp_path, faal_op="ruff", TEST_DB_NAME="raaktest_proef")

    assert klaar.returncode != 0, "a failing ruff must stop the script"
    aanroepen = spoor.read_text()
    assert "ruff format --check" in aanroepen, "ruff format --check does not run"
    assert "mypy" not in aanroepen, "mypy ran although ruff failed"
    assert "-m pytest" not in aanroepen, "pytest ran although ruff failed"


def test_ruff_check_runs_too(tmp_path):
    """The formatter and the linter are two commands; CI blocks on both."""
    klaar, spoor = _draai(
        tmp_path, script=_script_with_a_stub_css_build(tmp_path), TEST_DB_NAME="raaktest_proef"
    )

    assert klaar.returncode == 0, klaar.stderr
    aanroepen = spoor.read_text().splitlines()
    assert any("ruff format --check" in regel for regel in aanroepen)
    assert any("ruff check" in regel for regel in aanroepen)


def test_ruff_runs_as_a_module(tmp_path):
    """#1891: in a helper container built fresh, pip installs for the image's user
    outside the PATH — the bare `ruff` was not found there, `python -m ruff` is.

    Broken to check that this can go red (run, not reasoned): `python -m` taken
    off the `ruff check` line → the second assert fails.
    """
    klaar, spoor = _draai(
        tmp_path, script=_script_with_a_stub_css_build(tmp_path), TEST_DB_NAME="raaktest_proef"
    )

    assert klaar.returncode == 0, klaar.stderr
    aanroepen = spoor.read_text().splitlines()
    assert any(" python -m ruff format --check" in regel for regel in aanroepen)
    assert any(" python -m ruff check" in regel for regel in aanroepen)


def test_the_full_run_uses_four_processes(tmp_path):
    klaar, spoor = _draai(
        tmp_path, script=_script_with_a_stub_css_build(tmp_path), TEST_DB_NAME="raaktest_proef"
    )

    assert klaar.returncode == 0, klaar.stderr
    assert " -n 4 --dist loadgroup" in _pytest_call(spoor)


@pytest.mark.parametrize(
    ("argumenten", "omgeving"),
    [
        (("tests/test_iets.py",), {}),
        (("-k", "naam"), {}),
        ((), {"SNEL": "1"}),
    ],
)
def test_a_partial_run_stays_in_one_process(tmp_path, argumenten, omgeving):
    """A selection is not split: one test in four processes only pays four setups."""
    klaar, spoor = _draai(
        tmp_path,
        script=_script_with_a_stub_css_build(tmp_path),
        argumenten=argumenten,
        TEST_DB_NAME="raaktest_proef",
        **omgeving,
    )

    assert klaar.returncode == 0, klaar.stderr
    call = _pytest_call(spoor)
    assert " -n " not in call, f"a partial run was split over processes: {call}"
    for argument in argumenten:
        assert argument in call, "the selection did not reach pytest"


def test_the_guard_admits_the_database_of_a_worker(tmp_path):
    """Under four processes the suite runs on `<base>_gw0` … `_gw3` (CR-29 F1)."""
    klaar, spoor = _draai(
        tmp_path,
        script=_script_with_a_stub_css_build(tmp_path),
        TEST_DB_NAME="raaktest_proef_gw0",
    )

    assert klaar.returncode != 2, klaar.stderr
    assert spoor.exists(), "the script refused the name of a worker's database"

"""#777 — alembic mag andermans loggers niet uitzetten.

`backend/alembic/env.py` leest de logconfiguratie met `fileConfig(...)`. Die functie
staat standaard op `disable_existing_loggers=True` en zet dus `disabled = True` op
élke logger die op dat moment al bestaat. Alembic heeft daar geen reden voor: ze wil
enkel haar eigen configuratie inlezen.

**Op de server speelt het niet.** `startup.sh` draait `alembic upgrade head` als een
apart proces vóór uvicorn, dus daar zet het loggers uit die daarna toch verdwijnen.
In de tests draait conftest alembic in hetzelfde proces, en daar was het gevolg wél
merkbaar: `caplog` zag niets meer van `app.*`.

**Waarom dat erger is dan het klinkt.** Er vallen geen logregels weg op productie —
er valt een hele soort tests weg. Een assertie op een logregel meet dan niets en
staat tóch groen. Dat is de vorm die `CLAUDE.md` "hij kijkt nergens" noemt, dezelfde
als de veertien gates uit #678. Het werd actueel met de vier `STT-sessie`-regels uit
#772, die er juist zijn om op te kunnen toetsen.

De echte gedragsproef staat in `test_stt_stille_uitkomst.py`: dáár draait conftest
alembic in dit proces en leest `caplog` daarna gewoon de regels van de route. Zou
deze parameter terugdraaien, dan vallen die vier tests om. Wat hier staat is het
mechanisme zelf, uit elkaar gehaald.
"""
import logging
from logging.config import fileConfig
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_agnostisch

BACKEND = Path(__file__).resolve().parents[1]
ENV_PY = (BACKEND / "alembic" / "env.py").read_text()
ALEMBIC_INI = BACKEND / "alembic.ini"


def test_env_py_laat_bestaande_loggers_met_rust():
    assert "fileConfig(config.config_file_name, disable_existing_loggers=False)" in ENV_PY, (
        "alembic zet bij het inlezen van zijn eigen logconfiguratie de app-loggers uit")


@pytest.fixture
def herstel_logging():
    """Zet root-handlers en -niveau terug: `fileConfig` vervangt ze.

    Zonder dit zou de test de handler van `caplog` onder de rest van de suite
    vandaan trekken — en dan is de reparatie erger dan de kwaal.
    """
    root = logging.getLogger()
    handlers, niveau = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(niveau)


def test_de_parameter_is_precies_wat_het_verschil_maakt(herstel_logging):
    """De tegenproef, en ze is het hele punt.

    Twee identieke loggers, dezelfde echte `alembic.ini`, één verschil: de parameter.
    Zonder haar staat de logger daarna uit — dát is het gedrag dat we niet willen, en
    dat het bewijst dat de parameter draagt en niet meelift op iets anders.
    """
    uit = logging.getLogger("app.test777.zonder")
    aan = logging.getLogger("app.test777.met")

    fileConfig(ALEMBIC_INI, disable_existing_loggers=True)
    assert uit.disabled, (
        "de standaard van fileConfig zet bestaande loggers níet uit — dan is dit "
        "issue er nooit geweest en toetst deze test niets")

    uit.disabled = False  # de vorige aanroep raakte ze allebei
    aan.disabled = False
    fileConfig(ALEMBIC_INI, disable_existing_loggers=False)
    assert not aan.disabled and not uit.disabled, (
        "met disable_existing_loggers=False blijft een bestaande logger gewoon aan")

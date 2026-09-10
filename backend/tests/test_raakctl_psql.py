"""#818 — databankvragen per omgeving, en standaard alleen-lezen.

Tijdens de v2.0.0/v2.1.0-uitrol was dit het vaakst nodige waar `raakctl` geen verb
voor had: een tiental handgeschreven aanroepen met een compose-bestand, een
env-bestand, een containernaam en twee niveaus aanhalingstekens. Een vergeten `-T`
geeft een onbegrijpelijke fout; een verkeerde `<env>` draait je query op de verkeerde
databank, en dát is de fout met de ergste afloop.

**Twee eigenschappen worden hier getoetst, en beide moeten kunnen falen.**

1. *Een onbekende omgeving weigert vóór er iets uitgevoerd wordt.* Weigeren nádat de
   verbinding gelegd is, is geen weigering.
2. *Alleen-lezen is de standaard, op élke omgeving.* De rem is
   `default_transaction_read_only` van de server zelf en niet een blik op je SQL: een
   regex over een query is giswerk, Postgres die de schrijfactie weigert is een feit.
   Schrijven kan met `--write`, en op PROD alleen mét `--confirm`.

Het script draait hier echt, met een neppe `docker` in het PATH die noteert wat het
zou uitvoeren. Die notitie ís de assertie.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: de `PGOPTIONS`-regel
uit `cmd_psql` gehaald → de alleen-lezen-tests vallen om; de `case`-controle op de
omgeving weggehaald → de weigertest valt om.
"""
import os
import subprocess
from pathlib import Path

import pytest

RAAKCTL = Path(__file__).resolve().parents[2] / "raakctl"

pytestmark = pytest.mark.ui_agnostisch

ALLEEN_LEZEN = "default_transaction_read_only=on"


def _omgeving(tmp_path):
    """Neppe checkouts voor alle drie de omgevingen, plus een neppe `docker`."""
    spoor = tmp_path / "aanroepen.txt"
    env = dict(os.environ)
    for naam in ("hdev", "uat", "prod"):
        checkout = tmp_path / naam
        (checkout / ".git").mkdir(parents=True)
        (checkout / f"docker-compose.{naam}.yml").write_text("services: {}\n")
        (checkout / f".env.{naam}").write_text("\n")
        env[f"DEPLOY_{naam.upper()}_DIR"] = str(checkout)

    nepbin = tmp_path / "bin"
    nepbin.mkdir()
    # `ps -q db` moet iets teruggeven, anders weigert het verb terecht met "de
    # db-container draait niet" en toetsen we die weigering in plaats van de rest.
    nep = nepbin / "docker"
    nep.write_text(
        f'#!/bin/sh\necho "docker $@" >> "{spoor}"\n'
        'case "$*" in *"ps -q db"*) echo nepcontainer ;; esac\nexit 0\n')
    nep.chmod(0o755)

    env["PATH"] = f"{nepbin}:{env['PATH']}"
    return env, spoor


def _draai(tmp_path, *args, stdin=""):
    env, spoor = _omgeving(tmp_path)
    klaar = subprocess.run(["bash", str(RAAKCTL), *args], env=env, input=stdin,
                           capture_output=True, text=True, timeout=60)
    return klaar, (spoor.read_text() if spoor.exists() else "")


@pytest.mark.parametrize("omgeving", ["hdev", "uat", "prod"])
def test_lezen_gaat_standaard_alleen_lezen(omgeving, tmp_path):
    """Op élke omgeving, ook op hdev: de rem mag geen prod-uitzondering zijn, anders
    oefen je nergens met de vorm waarin je uiteindelijk werkt."""
    klaar, aanroepen = _draai(tmp_path, "psql", omgeving, "-c", "SELECT 1")

    assert klaar.returncode == 0, klaar.stderr
    assert ALLEEN_LEZEN in aanroepen, (
        f"de sessie draait niet alleen-lezen:\n{aanroepen}")
    assert f"docker-compose.{omgeving}.yml" in aanroepen, "verkeerde omgeving"
    assert "SELECT 1" in aanroepen


def test_write_haalt_de_rem_eraf(tmp_path):
    """De tegenproef: zonder haar zou een test die 'alleen-lezen' ziet ook groen staan
    als het verb nooit iets anders kán."""
    klaar, aanroepen = _draai(tmp_path, "psql", "hdev", "--write", "-c", "UPDATE x SET y=1")

    assert klaar.returncode == 0, klaar.stderr
    assert ALLEEN_LEZEN not in aanroepen
    assert "WRITEABLE" in klaar.stderr, "je ziet niet dat je in de schrijfstand zit"


def test_schrijven_op_prod_vraagt_een_bevestiging(tmp_path):
    klaar, aanroepen = _draai(tmp_path, "psql", "prod", "--write", "-c", "UPDATE x SET y=1")

    assert klaar.returncode != 0, "PROD liet een schrijfsessie zonder bevestiging toe"
    assert "--confirm" in klaar.stderr
    assert "psql" not in aanroepen, "er is al iets uitgevoerd vóór de weigering"


def test_schrijven_op_prod_mag_met_confirm(tmp_path):
    """Anders is de vorige test niet te onderscheiden van 'prod kan helemaal niet'."""
    klaar, aanroepen = _draai(tmp_path, "psql", "prod", "--write", "--confirm",
                              "-c", "UPDATE x SET y=1")

    assert klaar.returncode == 0, klaar.stderr
    assert ALLEEN_LEZEN not in aanroepen
    assert "docker-compose.prod.yml" in aanroepen


def test_een_onbekende_omgeving_weigert_voor_er_iets_gebeurt(tmp_path):
    """De fout met de ergste afloop is een query op de verkeerde databank."""
    klaar, aanroepen = _draai(tmp_path, "psql", "produktie", "-c", "SELECT 1")

    assert klaar.returncode != 0
    assert "produktie" in klaar.stderr
    assert aanroepen == "", (
        f"er werd al iets uitgevoerd vóór de weigering:\n{aanroepen}")


def test_een_andere_databank_kan_gekozen_worden(tmp_path):
    """`umami_<env>` was tijdens dezelfde uitrol herhaaldelijk nodig."""
    _klaar, aanroepen = _draai(tmp_path, "psql", "hdev", "--db", "umami_hdev",
                               "-c", "SELECT 1")

    assert "RAAKCTL_DB=umami_hdev" in aanroepen


def test_een_sql_bestand_gaat_over_stdin(tmp_path):
    """psql draait in de container en ziet jouw bestand niet; -f moet dus vertaald
    worden naar stdin en niet doorgegeven."""
    query = tmp_path / "vraag.sql"
    query.write_text("SELECT count(*) FROM members;\n")

    klaar, aanroepen = _draai(tmp_path, "psql", "uat", "-f", str(query))

    assert klaar.returncode == 0, klaar.stderr
    assert "exec -T" in aanroepen, "zonder -T hangt een niet-interactieve sessie"
    assert str(query) not in aanroepen, (
        "het pad werd aan psql doorgegeven; in de container bestaat het niet")


def test_een_ontbrekend_sql_bestand_wordt_meteen_gemeld(tmp_path):
    klaar, aanroepen = _draai(tmp_path, "psql", "hdev", "-f", str(tmp_path / "weg.sql"))

    assert klaar.returncode != 0
    assert "no such SQL file" in klaar.stderr
    assert aanroepen == ""


def test_het_verb_staat_in_de_hulptekst(tmp_path):
    """#678: een test die niets aantreft en toch groen staat, bewaakt niets."""
    env, _spoor = _omgeving(tmp_path)
    klaar = subprocess.run(["bash", str(RAAKCTL), "help"], env=env,
                           capture_output=True, text=True, timeout=60)
    hulp = klaar.stdout + klaar.stderr

    assert "raakctl psql" in hulp, "het verb staat niet in de hulp"
    assert "READ-ONLY" in hulp, (
        "de hulp zegt niet dat lezen de standaard is — dan verwacht je een schrijfsessie")

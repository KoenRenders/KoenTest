"""#753 — `raakctl restart` mag nooit bouwen of git aanraken.

Een stack herstarten om een gewijzigde env-var op te pikken vroeg twee commando's
plus kennis die nergens stond. Nu is het één verb.

**Deze test is er om één reden**, en het is niet de gemakzucht: `restart` en
`deploy` moeten uit elkaar blijven. Een restart geeft dezelfde code een nieuwe
configuratie; hij verandert niet wát er draait. Groeit dit verb ooit een build of
een git-actie, dan verandert er code op een omgeving zonder dat iemand `deploy`
heeft getypt — en dat is precies het soort stille verschuiving dat je pas merkt als
er iets stuk is.

Getoetst met een neppe `docker` en `git` in het PATH: het script draait echt, maar
raakt niets aan. Wat het aanroept wordt genoteerd, en daar hoort geen `build`,
`pull` of `checkout` in te staan.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `compose "$env"
build` toegevoegd aan `cmd_restart` → de vangrailtest valt om met die regel erbij;
het `--confirm`-blok weggehaald → de UAT-test valt om.
"""
import os
import subprocess
from pathlib import Path

import pytest

RAAKCTL = Path(__file__).resolve().parents[2] / "raakctl"

pytestmark = pytest.mark.ui_agnostisch


def _omgeving(tmp_path):
    """Een neppe checkout plus neppe `docker`/`git`, zodat het script echt draait."""
    checkout = tmp_path / "hdev"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "docker-compose.hdev.yml").write_text("services: {}\n")
    (checkout / ".env.hdev").write_text("\n")

    spoor = tmp_path / "aanroepen.txt"
    nepbin = tmp_path / "bin"
    nepbin.mkdir()
    for naam in ("docker", "git"):
        nep = nepbin / naam
        nep.write_text(f'#!/bin/sh\necho "{naam} $@" >> "{spoor}"\nexit 0\n')
        nep.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{nepbin}:{env['PATH']}"
    env["DEPLOY_HDEV_DIR"] = str(checkout)
    env["DEPLOY_UAT_DIR"] = str(checkout)
    return env, spoor


def _draai(tmp_path, *args):
    env, spoor = _omgeving(tmp_path)
    klaar = subprocess.run(["bash", str(RAAKCTL), *args], env=env,
                           capture_output=True, text=True, timeout=60)
    return klaar, (spoor.read_text() if spoor.exists() else "")


def test_restart_stopt_en_start_zonder_te_bouwen(tmp_path):
    klaar, aanroepen = _draai(tmp_path, "restart", "hdev")

    assert klaar.returncode == 0, klaar.stderr
    assert "compose" in aanroepen and " stop" in aanroepen, "er is niets gestopt"
    assert "up -d" in aanroepen, "de stack is niet opnieuw gestart"
    for verboden in (" build", " pull", "git "):
        assert verboden not in aanroepen, (
            f"restart voerde '{verboden.strip()}' uit — dat hoort bij deploy:\n{aanroepen}")


def test_restart_kan_een_enkele_service(tmp_path):
    """De wijziging die dit issue uitlokte raakte alleen de backend."""
    _klaar, aanroepen = _draai(tmp_path, "restart", "hdev", "backend")

    assert "stop backend" in aanroepen
    assert "up -d backend" in aanroepen


def test_uat_vraagt_een_bevestiging(tmp_path):
    """Zoals `deploy` die vraagt: een herstart onderbreekt echte bezoekers.

    En de tegenproef staat in de eerste test: op HDEV mag het zonder — dat is waar
    je dingen uitprobeert.
    """
    klaar, aanroepen = _draai(tmp_path, "restart", "uat")

    assert klaar.returncode != 0, "UAT herstartte zonder bevestiging"
    assert "--confirm" in klaar.stderr
    assert aanroepen == "", "er is al iets aangeraakt vóór de weigering"


def test_de_hulptekst_noemt_het_verschil_met_deploy(tmp_path):
    """Daar zit de verwarring, dus daar hoort het antwoord te staan."""
    env, _spoor = _omgeving(tmp_path)
    klaar = subprocess.run(["bash", str(RAAKCTL), "help"], env=env,
                           capture_output=True, text=True, timeout=60)
    hulp = klaar.stdout + klaar.stderr

    assert "restart" in hulp, "het verb staat niet in de hulp"
    assert "no git, no build" in hulp, (
        "de hulp zegt niet dat restart geen deploy is — precies de verwarring")

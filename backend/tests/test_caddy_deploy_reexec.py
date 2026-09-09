"""#796 — `deploy-caddy.sh` mag niet afbreken op verouderde logica.

De gedeelde Caddy bedient UAT én PROD, en haar deploy-script staat in een checkout
die achter kan lopen. Het `#162`-patroon lost dat op: bijwerken naar master en
éénmaal her-uitvoeren. Maar de re-exec stond ONDER de beslissingen.

**Waarom dat uitmaakt, preciezer dan "de oude versie beslist":** een `exec` herstart
het script van boven af, dus alles vóór dat punt doet de nieuwe versie gewoon
opnieuw. Wat níet goedkomt, is een pad dat vóór de re-exec **afbreekt**. Er staan
twee `exit 1`-en in dat gebied — "kon niet bepalen welke tag PROD draait" en de
vangrail voor de gemengde toestand (#572) — en een verouderde versie daarvan kan de
run afbreken zonder dat de update ooit gebeurt, of een geval nog niet kennen en
gewoon doorlopen.

Dat is bij de v2.0.1-uitrol misgegaan: `raak caddy v2.0.1` faalde op "'encode'
ontbreekt in caddy/Caddyfile.shared" terwijl `encode` in `caddy/parts/snippets.caddy`
stond. Een tweede aanroep liep door, want de eerste had de checkout intussen
bijgewerkt.

**De test bouwt precies die situatie na** in plaats van te controleren waar de
re-exec in het bestand staat — dat laatste is een grep. In een wegwerpmap staat een
OUDE scriptversie waarin één afbreekmelding herkenbaar anders luidt; een neppe `git`
op het PAD doet bij `reset --hard origin/master` wat de echte doet: hij zet de
ECHTE versie uit de werkmap op zijn plaats. Draait het script daarna verder en zien
we de NIEUWE melding, dan heeft het zichzelf eerst bijgewerkt.

Waarom een neppe `git` en geen echte repo: de testcontainer heeft geen `git`. Wat we
hier moeten nabootsen is bovendien klein en scherp omschreven — "de reset zet de
nieuwe scriptinhoud neer" — en dat is precies de aanname waar #796 op rust.

Kapotgemaakt om te controleren dat deze test rood kan worden: het re-exec-blok terug
onder de ref-afleiding gezet → de oude melding verschijnt en de test valt om.
"""
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_agnostisch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy-caddy.sh"

# Deze zin staat in de echte afbreekmelding; de oude versie in de fixture krijgt een
# andere, zodat de uitvoer verraadt wélke versie besliste.
NIEUWE_MELDING = "kon niet bepalen welke tag PROD draait"
OUDE_MELDING = "OUDE VERSIE besliste"


def _bouw(tmp_path):
    """Een checkout met de OUDE scriptversie, en een neppe git die naar de nieuwe
    bijwerkt."""
    echt = SCRIPT.read_text()
    oud = echt.replace(NIEUWE_MELDING, OUDE_MELDING)
    assert oud != echt, "de melding staat niet meer in het script — fixture kapot"

    checkout = tmp_path / "checkout"
    (checkout / "caddy" / "parts").mkdir(parents=True)
    (checkout / "caddy" / "Caddyfile.shared").write_text("# leeg\n")
    (checkout / "caddy" / "parts" / "snippets.caddy").write_text("# leeg\n")
    (checkout / "deploy-caddy.sh").write_text(oud)
    (checkout / "deploy-caddy.sh").chmod(0o755)

    nieuw_pad = tmp_path / "master-versie.sh"
    nieuw_pad.write_text(echt)

    nepbin = tmp_path / "bin"
    nepbin.mkdir()
    # De enige git-werking die #796 nodig heeft: `reset --hard origin/master` zet de
    # scriptinhoud van master neer. De rest is een no-op; `describe` blijft leeg,
    # zodat het script deterministisch afbreekt op "welke tag draait PROD?".
    (nepbin / "git").write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do\n'
        '  if [ "$a" = "--hard" ]; then\n'
        f'    cp "{nieuw_pad}" "{checkout}/deploy-caddy.sh"\n'
        "  fi\n"
        "done\n"
        "exit 0\n")
    (nepbin / "docker").write_text("#!/bin/sh\nexit 0\n")
    for f in nepbin.iterdir():
        f.chmod(0o755)
    return checkout, nepbin


def _draai(tmp_path):
    """Draait het script zonder argument en zonder ../prod, zodat het deterministisch
    afbreekt op "welke tag draait PROD?" — precies in het gebied dat #796 raakt."""
    checkout, nepbin = _bouw(tmp_path)
    env = dict(os.environ)
    env["PATH"] = f"{nepbin}:{env['PATH']}"
    env["PROD_CHECKOUT_DIR"] = str(tmp_path / "bestaat-niet")
    env["UAT_CHECKOUT_DIR"] = str(tmp_path / "bestaat-niet")
    return subprocess.run(["bash", "./deploy-caddy.sh"], cwd=checkout, env=env,
                          capture_output=True, text=True, timeout=120)


def test_het_script_werkt_zichzelf_bij_voor_het_beslist(tmp_path):
    klaar = _draai(tmp_path)
    uitvoer = klaar.stdout + klaar.stderr

    assert NIEUWE_MELDING in uitvoer, (
        "de melding van de nieuwe versie ontbreekt — het script is niet tot de "
        f"beslissing gekomen:\n{uitvoer[-2000:]}")
    assert OUDE_MELDING not in uitvoer, (
        "de OUDE scriptversie heeft beslist; de re-exec staat nog onder de "
        f"beslissingen:\n{uitvoer[-2000:]}")


def test_de_reexec_gebeurt_precies_een_keer(tmp_path):
    """De tegenproef op de vorige: onvoorwaardelijk her-uitvoeren zonder guard is een
    oneindige lus, en die zou hier als een timeout verschijnen in plaats van als een
    duidelijke fout. `CADDY_REEXEC` hoort dus één keer gezet te worden."""
    klaar = _draai(tmp_path)
    trace = klaar.stderr

    assert trace.count("export CADDY_REEXEC=1") == 1, (
        f"de re-exec is niet precies één keer gebeurd:\n{trace[-2000:]}")

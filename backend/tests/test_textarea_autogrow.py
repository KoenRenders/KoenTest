"""#1027 — elk meerregelig tekstvak groeit standaard mee.

Het gedrag bestond al (`autogrow`, #788) maar moest per veld meegegeven worden
en werd dus per veld vergeten: 2 van de 29 aanroepen hadden het. Nu zit het in
`textarea_control` zelf, met `max_px` als plafond en `autogrow=False` als
expliciete uitweg-met-reden.

Koens randvoorwaarde (19 september 2026): eenregelige velden mogen niet gaan
groeien. Die grens ligt in de macrokeuze — `input_control` rendert een
`<input>` en dit raakt alleen `<textarea>` — en wordt hier op een gerenderd
scherm met beide soorten velden vastgelegd, zodat het een eigenschap van de
code is en geen afspraak in een issue.

De poort tegen nieuwe rauwe `<textarea>`'s staat in
`test_ui_conventions_gate.py` (RAUWE_TEXTAREAS).

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `autogrow=True`
uit de macro-signatuur terug naar geen groei-attributen → de eerste twee tests
vallen om; de `{% if autogrow %}` weggehaald zodat ook de opt-out groeit → de
opt-out-test valt om.
"""
import re
from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

GROEI = 'x-init="$el.style.height'
TEMPLATES = Path(__file__).resolve().parents[1] / "app"


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _veld(html: str, veld_id: str) -> str:
    """De volledige openingstag van het veld met dit id."""
    m = re.search(rf'<(input|textarea)\b[^>]*id="{veld_id}"[^>]*>', html)
    assert m, f"veld {veld_id!r} niet gevonden"
    return m.group(0)


def test_omschrijving_groeit_en_naam_niet(client, db_session):
    """Het scherm uit Koens melding (#1016): de omschrijving van een activiteit
    groeit mee, het naamveld ernaast blijft één regel hoog."""
    from app.domains.activities.api import Activity

    a = Activity(name="Groeitest", location="Miloheem")
    db_session.add(a); db_session.commit()
    _login(client)

    html = client.get(f"/admin/activiteiten/{a.id}").text
    assert GROEI in _veld(html, "description")
    assert "Math.min($el.scrollHeight, 400)" in _veld(html, "description")
    naam = _veld(html, "name")
    assert naam.startswith("<input")
    assert GROEI not in naam and "scrollHeight" not in naam


def test_eigen_plafond_blijft_en_de_optout_groeit_niet(client):
    """De kitpagina toont beide standen: een vak met eigen `max_px` houdt dat
    plafond (en krijgt de attributen niet dubbel), de opt-out draagt géén
    groei-attributen."""
    _login(client)
    html = client.get("/admin/design-system").text

    groeiend = _veld(html, "ds-omschrijving")
    assert "Math.min($el.scrollHeight, 200)" in groeiend
    assert groeiend.count("x-init") == 1, "de groei-attributen staan er dubbel op"

    vast = _veld(html, "ds-notities")
    assert GROEI not in vast and "scrollHeight" not in vast


def test_de_twee_bewuste_afwijkingen_staan_met_reden_in_de_bron():
    """Het Raakje-veld houdt zijn plafond van 240; de verborgen HTML-bron-editor
    van de pagina-editor groeit niet (x-init zou op een verborgen element
    scrollHeight 0 lezen en de hoogte op nul pinnen)."""
    raakje = (TEMPLATES / "domains/newsletter/templates/_nb_raakje.html").read_text()
    assert "max_px=240" in raakje
    assert "ui.autogrow" not in raakje  # niet én de standaard én de oude attrs

    cp = (TEMPLATES / "domains/cms/templates/_cp_detail.html").read_text()
    bron_editor = cp[cp.index('id="cp-htmlsrc"') - 400:cp.index('id="cp-htmlsrc"') + 400]
    assert "autogrow=False" in bron_editor

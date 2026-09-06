"""#693 — het CSRF-token stond leeg in `hx-headers` op de publieke schil.

Dit is de oorzaak onder de 403's van #649/#662, waar bewust géén zelfherstel kwam
zolang die onbekend was.

Het token staat in `hx-headers` op de `<body>` van de schil. Bij een
`hx-boost`-navigatie vervangt htmx de **inhoud** van de body, niet haar
**attributen** — dus het token blijft staan zoals de éérste pagina hem zette. En de
meeste publieke pagina's zetten er geen: `site_context` leverde er geen, dus
`{{ csrf_token|default("") }}` werd een lege tekenreeks. Landde je via zo'n pagina
en boostte je daarna naar `/leden/gezin`, dan verstuurde elke mutatie een leeg
token.

Herladen hielp omdat dat een harde navigatie is — vandaar dat het advies in de
melding klopte terwijl de verklaring erin niet klopte.

**Deze tests toetsen de WAARDE, niet de aanwezigheid van het attribuut.** Het
attribuut stond er al, met een lege waarde erin: een assertie op aanwezigheid stond
vóór deze fix groen en bewees niets.

En ze lopen over **élke** basisroute van de schil. Het probleem ontstond juist
doordat sommige routes het token wél zetten en andere niet, dus één steekproef had
het gemist.
"""
import re

import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_postal_code

pytestmark = pytest.mark.ui_agnostisch

HEADERS = re.compile(r'hx-headers=\'\{"X-CSRF-Token": "([^"]*)"\}\'')

PUBLIEK = ["/", "/activiteiten", "/fotos", "/lid-worden", "/aanmelden", "/berichten"]
ADMIN = ["/admin", "/admin/leden", "/admin/activiteiten", "/admin/betalingen",
         "/admin/formulieren", "/admin/paginas", "/admin/media", "/admin/gebruikers",
         "/admin/werkbank", "/admin/e-maillog", "/admin/tenants"]


def _token_uit(html: str):
    treffer = HEADERS.search(html)
    assert treffer is not None, "de schil draagt geen hx-headers met een CSRF-token"
    return treffer.group(1)


@pytest.mark.parametrize("pad", PUBLIEK)
def test_elke_publieke_pagina_draagt_een_gevuld_token(client, db_session, pad):
    """De kern van #693: leeg is het probleem, niet afwezig."""
    seed_postal_code(db_session)
    resp = client.get(pad)
    if resp.status_code in (302, 404):
        pytest.skip(f"{pad} bestaat niet of leidt door in deze opzet")
    assert resp.status_code == 200, resp.text[:200]

    token = _token_uit(resp.text)
    assert token, f"{pad} zet een LEEG CSRF-token — precies de fout van #693"


@pytest.mark.parametrize("pad", PUBLIEK)
def test_het_token_hoort_bij_de_sessie_van_de_bezoeker(client, db_session, pad):
    """Gevuld is niet genoeg: het moet ook het júiste token zijn. Een willekeurige
    constante zou de test hierboven ook groen zetten, en `require_csrf` zou hem
    daarna alsnog weigeren."""
    seed_postal_code(db_session)
    waarde = make_session_value("lid@example.com")
    client.cookies.set(SESSION_COOKIE, waarde)

    resp = client.get(pad)
    if resp.status_code in (302, 404):
        pytest.skip(f"{pad} bestaat niet of leidt door in deze opzet")
    assert _token_uit(resp.text) == csrf_token_for(waarde)


@pytest.mark.parametrize("pad", ADMIN)
def test_elke_beheerpagina_draagt_het_juiste_token(client, db_session, pad):
    """Hetzelfde mechanisme, dezelfde stille fout: een adminroute die het token niet
    meegeeft zou net zo onopgemerkt blijven."""
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)

    resp = client.get(pad)
    if resp.status_code in (302, 403, 404):
        pytest.skip(f"{pad} is hier niet bereikbaar ({resp.status_code})")
    assert resp.status_code == 200, resp.text[:200]
    assert _token_uit(resp.text) == csrf_token_for(waarde), (
        f"{pad} zet een leeg of verkeerd CSRF-token")


# ── Het vangnet in de boosted swap ──────────────────────────────────────────

def test_de_boosted_swap_neemt_hx_headers_over(client, db_session):
    """Een bronregel, want JavaScript draait hier niet.

    Dit is het vangnet voor het geval dat de melding beschrijft en dat wél echt
    bestaat: opnieuw inloggen in een ander venster verandert de cookie, en dan klopt
    de waarde in de huidige body niet meer. De schilcontrole las de respons toch al;
    het token overnemen is één regel erbij.
    """
    html = client.get("/").text
    assert "getAttribute('hx-headers')" in html, (
        "de swap-handler leest hx-headers niet uit het antwoord")
    assert "setAttribute('hx-headers'" in html, (
        "de swap-handler neemt hx-headers niet over")


def test_de_melding_beweert_geen_oorzaak_meer(client, db_session):
    """De oude tekst zei dat de sessie in een ander venster vernieuwd was. Dat is
    aantoonbaar zelden de oorzaak — `set_session_cookie` heeft twee aanroepplaatsen,
    inloggen en een magic link, dus de cookie roteert niet tijdens het browsen.

    Een melding die een verkeerde oorzaak noemt, stuurt wie hem leest de verkeerde
    kant op: bij #662 werd maandenlang naar sessieverloop gezocht.
    """
    html = client.get("/").text
    assert "vernieuwd in een ander venster" not in html, (
        "de melding beweert nog altijd een oorzaak die zelden klopt")
    assert "beveiligingscontrole ging niet door" in html, (
        "de neutrale melding ontbreekt")

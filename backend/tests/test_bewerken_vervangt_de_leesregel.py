"""#648 — een bewerkformulier vervangt de leesregel, het staat er niet onder.

Op /admin/activiteiten/<id> bleef bij Datums de leesregel staan zodra je Bewerken
klikte, en kwam het formulier eronder. Dezelfde datum stond dan twee keer op het
scherm: één keer als tekst, één keer in de invulvelden — en wie het veld wijzigde,
zag de oude waarde er nog boven staan.

Het adresblok in het gezinsdetail doet het wél goed sinds #639. Dat is het
patroon: leesregel achter `x-show="!<state>"`, een korte vervangtekst in haar
plaats, en de knop blijft staan.

Deze test leest de opgemaakte HTML en toetst het paar leesregel/formulier per
toggle. Dat de leesregel dan ook echt verdwijnt is Alpine-gedrag en wordt in
tests_e2e/test_foutzichtbaarheid.py's zusterbestand in een echte browser bewezen.
"""

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _detail(client, activity_id: int) -> str:
    r = client.get(f"/admin/activiteiten/{activity_id}")
    assert r.status_code == 200
    return r.text


def test_de_koppen_blijven_wel_staan(client, db_session):
    """Bewuste keuze, zie #648: bij de activiteit- en onderdeelKOP blijft de
    leesweergave staan.

    Een kop is geen herhaling van het formulier maar het antwoord op "wat ben ik
    aan het bewerken". Met meerdere onderdeelkaarten op één scherm zou een open
    formulier zonder titel niet meer aanwijsbaar zijn. Bij de regels speelt dat
    niet: het formulier staat daar precies op de plaats van de regel zelf.
    """
    activity, comp, _p = seed_activity_with_product(db_session)
    _login(client)
    html = _detail(client, activity.id)

    # Sinds de feedbackronde van 15 sep (golf 8) draagt de recordkop (h1) de
    # naam en heet de kaartkop "Activiteit"; de onderdeelkop draagt zijn naam.
    for kop, tekst in (("h2", "Activiteit"), ("h3", comp.name)):
        m = re.search(rf"<{kop}[^>]*>(?:(?!</{kop}>).)*{re.escape(tekst)}", html, re.S)
        assert m, f"de {kop}-kop met {tekst!r} staat niet op het scherm"
        assert "x-show" not in m.group(0), (
            f"de {kop}-kop is verborgen tijdens het bewerken; dat was niet de keuze"
        )

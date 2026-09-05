"""#653 — de huidige bijlage staat nooit twee keer tegelijk op het scherm.

`_aa_detail.html` had een alinea met "Huidige affiche bekijken" waarvan de
code-opmerking zei "in read-modus", maar zonder `x-show`. Ze stond er dus ook
tijdens het bewerken, waar `ui.upload_field()` diezelfde link al rendert.

§2.12: de leeslink mag blijven — een bijlage kunnen openen zonder eerst te gaan
bewerken is nuttig — maar dan uitsluitend achter `x-show="!edit"`.
"""
import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _regels_met(html: str, tekst: str) -> list[str]:
    return [r.strip() for r in html.splitlines() if tekst in r]


def test_de_affichelink_staat_er_twee_keer_maar_nooit_tegelijk(client, db_session):
    """Twee voorkomens is juist — één per modus. Ze horen elkaar uit te sluiten."""
    activity, _c, _p = seed_activity_with_product(db_session)
    activity.poster_url = None
    db_session.flush()
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text

    regels = _regels_met(html, "Huidige affiche bekijken")
    assert len(regels) == 2, (
        f"verwacht één leeslink en één in het uploadblok, kreeg er {len(regels)}")
    lees = [r for r in regels if 'x-show="!edit"' in r]
    assert len(lees) == 1, (
        "de leeslink hangt niet aan de leesmodus en staat dus ook tijdens het "
        f"bewerken op het scherm (#653):\n  " + "\n  ".join(regels))


def test_ook_de_locatie_hangt_aan_de_leesmodus(client, db_session):
    """Zelfde fout, gevonden bij het schrijven van de lintregel: de locatie bleef
    staan terwijl je ze in het formulier aan het wijzigen was."""
    activity, _c, _p = seed_activity_with_product(db_session)
    activity.location = "Parochiezaal"
    db_session.flush()
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text

    leesregels = [r for r in _regels_met(html, "Parochiezaal") if "<input" not in r]
    assert leesregels, "de locatie staat niet als leesregel op het scherm"
    assert all('x-show="!edit"' in r for r in leesregels), (
        "de locatie blijft staan tijdens het bewerken:\n  " + "\n  ".join(leesregels))


def test_zonder_bijlage_geen_leeslink(client, db_session):
    """De guard moet blijven staan: geen affiche, geen link."""
    activity, _c, _p = seed_activity_with_product(db_session)
    _login(client)
    html = client.get(f"/admin/activiteiten/{activity.id}").text

    # Het uploadblok toont het label enkel als er een bijlage is; de leeslink ook.
    assert "Huidige affiche bekijken" not in html

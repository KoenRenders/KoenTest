"""De omgevingsbanner staat niet op een schermafdruk, maar wel op het scherm (#1238).

De zestien afdrukken voor de publieke uitlegpagina droegen bovenaan de oranje balk
*"DEV — testomgeving (geen productie)"*. Voor een lid dat die uitleg leest is dat geen
eerlijke waarschuwing maar een verwarrende: ze gaat niet over zijn situatie.

**De tegenproef is hier het halve werk.** Een reparatie die de balk overal sloopt haalt
test 1 even gemakkelijk als de juiste — en dan raakt een testomgeving haar banner kwijt,
precies het ongeluk dat die banner moet voorkomen. Vandaar drie vormen, en de laatste twee
zijn de tegenproeven:

1. mét de vlag verdwijnt de balk, in beide schillen;
2. **zonder** de vlag — dezelfde pagina, dezelfde omgeving, een gewone browser — staat hij
   er nog;
3. met de vlag maar op een omgeving die niet `dev` is, staat hij er ook nog. Dat is het
   tweede slot op de deur: HDEV en UAT kunnen hun banner niet kwijtraken, wat een
   verzoek ook meestuurt.

Rood gemaakt om te toetsen dát ze kunnen falen: met `and not is_screenshot()` uit
`site_base.html` en `admin_base.html` gehaald faalt (1) in beide schillen; met de
`app_env != "dev"`-poort uit `app.ui._is_screenshot` gehaald faalt (3).
"""

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.ui import SCREENSHOT_HEADER
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

# De tekst uit `ui.env_banner` (_macros.html), niet de opmaak: dit is de balk zoals een
# bezoeker hem leest. Zou de tekst wijzigen, dan wijst deze test naar de macro.
BANNER = "testomgeving (geen productie)"

VLAG = {SCREENSHOT_HEADER: "1"}


def _als_beheerder(client, db):
    """Een sessie voor de beheerschil — de reeks fotografeert daar zes schermen."""
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "ADMIN" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _publiek(client, headers=None):
    resp = client.get("/", headers=headers or {})
    assert resp.status_code == 200, f"/ → {resp.status_code}"
    return resp.text


def _beheer(client, db, headers=None):
    _als_beheerder(client, db)
    resp = client.get("/admin", headers=headers or {})
    assert resp.status_code == 200, f"/admin → {resp.status_code}"
    return resp.text


def test_een_afdruk_van_een_publiek_scherm_draagt_de_balk_niet(client):
    assert BANNER not in _publiek(client, VLAG)


def test_een_afdruk_van_een_beheerscherm_draagt_de_balk_niet(client, db_session):
    assert BANNER not in _beheer(client, db_session, VLAG)


def test_zonder_de_vlag_staat_de_balk_er_nog_op_hetzelfde_scherm(client):
    """De tegenproef: een gewone browser op diezelfde omgeving ziet de waarschuwing."""
    assert BANNER in _publiek(client)


def test_zonder_de_vlag_staat_de_balk_er_nog_in_de_beheerschil(client, db_session):
    assert BANNER in _beheer(client, db_session)


def test_the_header_is_the_same_with_and_without_the_banner(client):
    """Without the banner no gap of 24 px (`h-6`) may stay above the header (#610).

    Since #1588 the banner stands in the document flow on the public shell and
    the header sticks at y 0 through `.site-header`, so nothing has to move: the
    header's opening tag is the same on a screenshot and on the screen, and no
    offset for the banner's height exists in either.
    """
    import re

    def header_tag(html: str) -> str:
        found = re.search(r"<header\b[^>]*>", html)
        assert found, "the header was not found"
        return found.group(0)

    opname = _publiek(client, VLAG)
    scherm = _publiek(client)
    assert "data-env-banner" not in opname and "data-env-banner" in scherm
    assert header_tag(opname) == header_tag(scherm) == '<header class="site-header" :inert="menu">'
    for html in (opname, scherm):
        assert "top-6" not in html, "de offset voor de bannerhoogte staat er nog"


@pytest.mark.parametrize("omgeving", ["hdev", "uat"])
def test_op_een_echte_testomgeving_negeert_de_schil_de_vlag(client, monkeypatch, omgeving):
    """Het tweede slot: alleen APP_ENV=dev eert de vlag.

    `dev` is de enige waarde waartegen de opnametool ooit draait
    (`docker-compose.dev.yml`, `scripts/e2e-local.sh`, de e2e-job in CI), dus verder
    dan dat hoeft de vlag nooit te reiken. Een HDEV die haar banner kwijtraakt omdat
    iemand een header meestuurt, is precies wat we niet willen kunnen.
    """
    import app.ui

    monkeypatch.setattr(app.ui._settings, "app_env", omgeving)
    # `omgeving` in de template blijft de waarde van bij het importeren ("dev"); de
    # balk hoort dus te verschijnen omdat de vlag genegeerd wordt, niet omdat de
    # omgeving verandert.
    assert BANNER in _publiek(client, VLAG)

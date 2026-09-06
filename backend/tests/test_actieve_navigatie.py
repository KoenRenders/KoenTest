"""#714 — het actieve menu-item verspringt niet bij een gebooste navigatie.

Koen stond op `/admin/activiteiten` terwijl in de zijbalk nog "Leden" oplichtte.

**De server had het altijd al goed.** Elke module bouwt haar nav met het juiste
actieve pad en de routes geven die mee. Het antwoord kwam alleen nooit in beeld:
`_boosted_swap_headers` zet op élk geboost antwoord `HX-Reselect: #main`, dus alleen
de inhoud wordt vervangen en de zijbalk blijft letterlijk staan — met de markering van
het vorige scherm.

Die keuze is goed onderbouwd (geen flikkerende zijbalk, en `hx-target` op de body zou
naar élke htmx-actie overerven — de val uit #613/#616). Wat over het hoofd gezien
werd: **de zijbalk draagt toestand**, en die verandert bij elke navigatie.

**Geverifieerd vóór gekozen.** In de meegeleverde htmx 2.0.4 doet `swap()` eerst de
out-of-band-afhandeling en pas daarna het `select`-filter — dus een oob-element
overleeft `HX-Reselect`. Was die volgorde omgekeerd geweest, dan was de client-kant in
`htmx_ux()` de terugval geweest, met de regel op twee plaatsen als prijs.

**Wat deze tests wel en niet kunnen.** De uitkomst ná de swap gebeurt in de browser;
die staat in `tests_e2e/`. Hier toetsen we het **mechanisme** dat die swap mogelijk
maakt — dat de nav als oob meekomt — en dat is precies het stuk dat ontbrak. Een test
op "het antwoord bevat de juiste markering" stond vandaag al groen en bewijst niets.
"""
import re

import pytest

from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_postal_code

pytestmark = pytest.mark.ui_agnostisch

BOOST = {"HX-Request": "true", "HX-Boosted": "true"}


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _blok(html: str, element_id: str) -> str:
    """Het element met dit id, tot zijn sluittag."""
    start = html.index(f'id="{element_id}"')
    open_tag = html.rindex("<", 0, start)
    naam = re.match(r"<(\w+)", html[open_tag:]).group(1)
    return html[open_tag:html.index(f"</{naam}>", start)]


# ── 1. Het mechanisme: de nav komt mee als oob ─────────────────────────────

@pytest.mark.parametrize("element_id", ["admin-nav-zijbalk", "admin-nav-mobiel"])
def test_de_beheernav_komt_mee_als_oob(client, db_session, element_id):
    """Twee renderingen per schil: een fix die er één bijwerkt laat de andere fout
    staan, en op een telefoon zie je juist die tweede."""
    _login(client)
    html = client.get("/admin/activiteiten", headers=BOOST).text

    blok = _blok(html, element_id)
    assert 'hx-swap-oob="true"' in blok[:blok.index(">") + 1], blok[:200]


@pytest.mark.parametrize("element_id", ["site-nav-breed", "site-nav-mobiel"])
def test_de_publieke_nav_komt_mee_als_oob(client, db_session, element_id):
    """Dezelfde middleware, tweede symptoom: "Home" bleef onderstreept terwijl je op
    /leden/gezin stond."""
    seed_postal_code(db_session)
    html = client.get("/fotos", headers=BOOST).text

    blok = _blok(html, element_id)
    assert 'hx-swap-oob="true"' in blok[:blok.index(">") + 1], blok[:200]


# ── 2. De markering die meekomt, klopt ─────────────────────────────────────

def test_de_meegestuurde_zijbalk_markeert_het_juiste_scherm(client, db_session):
    """Het gemelde geval: op /admin/activiteiten lichtte "Leden" op."""
    _login(client)
    zijbalk = _blok(client.get("/admin/activiteiten", headers=BOOST).text,
                    "admin-nav-zijbalk")

    actief = [r for r in zijbalk.split("<a ") if "bg-white/20" in r]
    assert len(actief) == 1, f"{len(actief)} actieve items i.p.v. één"
    assert "/admin/activiteiten" in actief[0], actief[0][:200]


def test_een_ander_scherm_markeert_een_ander_item(client, db_session):
    """De keerzijde: zonder haar zou "markeer altijd hetzelfde" ook slagen."""
    _login(client)
    zijbalk = _blok(client.get("/admin/leden", headers=BOOST).text,
                    "admin-nav-zijbalk")

    actief = [r for r in zijbalk.split("<a ") if "bg-white/20" in r]
    assert len(actief) == 1 and "/admin/leden" in actief[0], actief[0][:200]


# ── 3. De bescherming uit #613/#616 blijft ─────────────────────────────────

def test_een_gewone_hx_post_krijgt_geen_reselect(client, db_session):
    """Nu die middleware toch aangeraakt is: alleen een gebooste NAVIGATIE hoort
    `HX-Reselect` te krijgen. Zou een gewone `hx-post` hem meekrijgen, dan wordt van
    elk formulier-antwoord alleen `#main` geplukt en verdwijnt het fragment waar de
    knop op mikte — de val uit #613/#616."""
    csrf = _login(client)
    resp = client.post("/admin/formulieren",
                       data={"title": "Zonder reselect"},
                       headers={"HX-Request": "true", "X-CSRF-Token": csrf})

    assert "HX-Reselect" not in resp.headers, dict(resp.headers)
    assert "HX-Retarget" not in resp.headers


def test_een_geboorde_navigatie_krijgt_hem_wel(client, db_session):
    """De keerzijde van hierboven: zonder deze test zou "zet nooit Reselect" ook
    slagen, en dan swapt elke navigatie de hele pagina in `#main`."""
    _login(client)
    resp = client.get("/admin/activiteiten", headers=BOOST)
    assert resp.headers.get("HX-Reselect") == "#main"

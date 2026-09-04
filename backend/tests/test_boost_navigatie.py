"""hx-boost: navigeren swapt de inhoud, niet de schil (#634).

De polish zelf (geen wit flitsmoment, zijbalk blijft staan) is browsergedrag en
staat in `tests_e2e`. Wat hier getoetst wordt is het contract dat dat gedrag
mogelijk maakt, en dat je in Python volledig kan nagaan:

1. Op een gebooste navigatie stuurt de server de drie swap-instructies mee als
   responsheaders (HX-Retarget/HX-Reselect/HX-Reswap).
2. Op een gewone htmx-actie — een `hx-post` die een fragment terugkrijgt — stuurt
   ze die juist NIET. Dat is de kern: stonden die instructies als
   hx-target/hx-select/hx-swap op de <body>, dan erfde élke actie in de app ze
   (htmx zoekt ze met een closest()-lookup) en zocht ze `#main` in een antwoord
   dat alleen een lijstfragment bevat — een knop die stil niets doet.
3. Er ís een `#main` om in te swappen, in beide schillen.
"""
import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value

from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

BOOST = {"HX-Request": "true", "HX-Boosted": "true"}
SWAP_HEADERS = ("HX-Retarget", "HX-Reselect", "HX-Reswap")


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def test_gebooste_navigatie_krijgt_de_swap_instructies(client):
    _login(client)
    r = client.get("/admin/leden", headers=BOOST)

    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#main"
    assert r.headers["HX-Reselect"] == "#main"
    assert r.headers["HX-Reswap"].startswith("outerHTML")
    assert 'id="main"' in r.text          # het doel bestaat ook echt


def test_publieke_schil_boost_op_dezelfde_manier(client):
    r = client.get("/", headers=BOOST)

    assert r.status_code == 200
    assert r.headers["HX-Reselect"] == "#main"
    assert 'id="main"' in r.text


def test_een_gewone_htmx_actie_krijgt_ze_niet(client):
    """Zonder HX-Boosted blijft alles zoals het was — anders breekt elke lijst."""
    _login(client)
    r = client.get("/admin/leden", headers={"HX-Request": "true"})

    assert r.status_code == 200
    for header in SWAP_HEADERS:
        assert header not in r.headers, (
            f"{header} op een niet-gebooste actie: die zou #main zoeken in een fragment")


def test_een_gewoon_paginaverzoek_krijgt_ze_niet(client):
    _login(client)
    r = client.get("/admin/leden")

    assert r.status_code == 200
    for header in SWAP_HEADERS:
        assert header not in r.headers


def test_beide_schillen_dragen_een_main(client):
    _login(client)
    for pad in ("/", "/admin/leden"):
        assert 'id="main"' in client.get(pad).text, f"{pad} mist #main"

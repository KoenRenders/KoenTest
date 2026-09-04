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
4. Een gebooste navigatie krijgt de **hele pagina**, niet het lijstfragment. Dat
   is de val waar #634 in liep: lijstschermen geven bij een htmx-verzoek alleen
   hun kaartenfragment terug (zoeken/filteren), en een gebooste klik draagt
   dezelfde `HX-Request`-header. Het scherm liep daardoor leeg — htmx zocht
   `#main` in een fragment dat het niet bevatte.
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


def test_een_gebooste_navigatie_krijgt_de_hele_pagina_geen_fragment(client):
    """De val van #634: `HX-Request` alleen onderscheidt de twee niet.

    Lijstschermen vertakken op "is dit een htmx-verzoek?" om bij zoeken/filteren
    alleen hun kaarten terug te geven. Een gebooste klik op een nav-link is óók
    een htmx-verzoek. Zonder het onderscheid (`HX-Boosted`) kreeg de schil een
    fragment zonder #main terug en verving htmx #main door niets — een leeg
    scherm, zonder foutmelding.
    """
    _login(client)
    for pad in ("/admin/leden", "/admin/activiteiten", "/admin/paginas",
                "/admin/formulieren", "/admin/gebruikers", "/admin/werkbank",
                "/admin/media", "/admin/tenants", "/admin/ledenwijzigingen"):
        geboost = client.get(pad, headers=BOOST)
        assert geboost.status_code == 200, pad
        assert 'id="main"' in geboost.text, f"{pad} gaf een fragment op een gebooste navigatie"
        assert "<html" in geboost.text.lower(), pad


def test_een_gewoon_htmx_verzoek_krijgt_nog_steeds_het_fragment(client):
    """De keerzijde: zoeken/filteren mag geen hele pagina terugsturen, anders
    nestelt de lijst zichzelf in de lijst."""
    _login(client)
    fragment = client.get("/admin/leden", headers={"HX-Request": "true"})
    assert fragment.status_code == 200
    assert "<html" not in fragment.text.lower()

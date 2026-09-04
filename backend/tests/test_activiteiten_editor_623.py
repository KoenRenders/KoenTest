"""Activiteiten-editor: aanmaken zonder popup, poster-URL, secties, uploads (#623).

De poster-URL was een echte regressie: `Activity.poster_url` bleef op het model en in
de schemas bestaan, maar het scherm bood het veld niet meer aan — je kon alleen nog
uploaden. Zulke stille regressies zijn de reden dat deze tests op het gerenderde
scherm kijken en niet alleen op de service.
"""
from datetime import date

import pytest

from app.domains.activities.api import Activity
from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for, make_session_value)
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def test_aanmaken_opent_een_volledige_pagina_geen_modal(client, db_session):
    """§2.8 sinds #627: aanmaken opent een volledige-pagina-editor. De lijst linkt
    ernaartoe i.p.v. een dialoogje te openen."""
    _login(client)
    lijst = client.get("/admin/activiteiten").text
    assert 'href="/admin/activiteiten/nieuw"' in lijst
    assert "ui.modal" not in lijst and 'x-data="{ open: false }"' not in lijst

    scherm = client.get("/admin/activiteiten/nieuw")
    assert scherm.status_code == 200
    assert 'name="name"' in scherm.text and 'name="start_date"' in scherm.text


def test_poster_url_wordt_bewaard(client, db_session):
    """De regressie van punt 2: het veld verdween uit het scherm terwijl het op het
    model bleef bestaan."""
    activity, _comp, _product = seed_activity_with_product(db_session, is_free=False)
    hdr = _login(client)

    detail = client.get(f"/admin/activiteiten/{activity.id}").text
    assert 'name="poster_url"' in detail, "het veld hoort in de bewerkvorm te staan"

    resp = client.post(f"/admin/activiteiten/{activity.id}", headers=hdr, data={
        "name": activity.name, "location": "", "poster_url": "https://voorbeeld.be/affiche.png",
        "members_only": "", "is_cancelled": ""})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    assert db_session.get(Activity, activity.id).poster_url == "https://voorbeeld.be/affiche.png"


def test_de_affiche_zit_in_dezelfde_vorm_als_de_tekstvelden(client, db_session):
    """Eén "Opslaan" voor tekstveld én bestand; geen aparte Uploaden-knop meer."""
    activity, _c, _p = seed_activity_with_product(db_session, is_free=False)
    _login(client)
    detail = client.get(f"/admin/activiteiten/{activity.id}").text

    assert 'enctype="multipart/form-data"' in detail
    assert 'hx-post="/admin/activiteiten/%d/affiche"' % activity.id not in detail, \
        "de aparte upload-route hoort niet meer in het scherm te staan"


def test_sectie_toevoegvormen_staan_dicht_tot_je_klikt(client, db_session):
    """#623-4: de toevoegvormen stonden permanent open, terwijl de meeste
    activiteiten één datum, één onderdeel en één product hebben."""
    activity, _c, _p = seed_activity_with_product(db_session, is_free=False)
    _login(client)
    detail = client.get(f"/admin/activiteiten/{activity.id}").text

    for vlag in ('x-show="adddate"', 'x-show="addcomp"', 'x-show="addprod"'):
        assert vlag in detail, f"{vlag} ontbreekt — de vorm staat permanent open"
    assert '_("+ Datum")' not in detail  # gerenderd, niet als broncode
    assert "+ Datum" in detail and "+ Product" in detail


def test_de_bijlage_kan_verwijderd_worden(client, db_session):
    """Ontbrak volledig: een verkeerd bestand kon je alleen overschrijven."""
    activity, comp, _p = seed_activity_with_product(db_session, is_free=False)
    hdr = _login(client)

    for pad in (f"/admin/activiteiten/{activity.id}/affiche/verwijderen",
                f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/info/verwijderen"):
        resp = client.post(pad, headers=hdr)
        assert resp.status_code == 200, f"{pad} → {resp.status_code}: {resp.text[:200]}"


def test_de_info_route_heet_niet_meer_reglement(client, db_session):
    """§2.12: één woord voor één ding."""
    activity, comp, _p = seed_activity_with_product(db_session, is_free=False)
    hdr = _login(client)

    assert client.post(f"/admin/activiteiten/{activity.id}/onderdelen/{comp.id}/info",
                       headers=hdr).status_code == 200
    detail = client.get(f"/admin/activiteiten/{activity.id}").text
    assert "reglement" not in detail.lower()

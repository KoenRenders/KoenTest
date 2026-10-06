"""Activiteiten-editor: aanmaken zonder popup, poster-URL, secties, uploads (#623).

De poster-URL was een echte regressie: `Activity.poster_url` bleef op het model en in
de schemas bestaan, maar het scherm bood het veld niet meer aan — je kon alleen nog
uploaden. Zulke stille regressies zijn de reden dat deze tests op het gerenderde
scherm kijken en niet alleen op de service.
"""

from pathlib import Path

import pytest

from app.domains.activities.api import Activity
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

APP = Path(__file__).resolve().parents[2] / "app"

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
    # Geen aanmaakdialoog meer in de lijst. `ui.modal` is templatebroncode, dus die
    # toets je op het bestand — niet op x-data, want de mobiele nav gebruikt dezelfde
    # Alpine-vlag.
    bron = (APP / "domains" / "activities" / "templates" / "admin_activiteiten.html").read_text()
    assert "{% call ui.modal(" not in bron

    scherm = client.get("/admin/activiteiten/nieuw")
    assert scherm.status_code == 200
    # #1649: that editor is the fiche itself, empty — no start screen first.
    assert 'name="name"' in scherm.text and 'name="d.n1.start_date"' in scherm.text
    assert 'id="aa-act-form"' in scherm.text and 'data-mode="edit"' in scherm.text


def test_poster_url_wordt_bewaard(client, db_session):
    """De regressie van punt 2: het veld verdween uit het scherm terwijl het op het
    model bleef bestaan."""
    activity, _comp, _product = seed_activity_with_product(db_session, is_free=False)
    hdr = _login(client)

    detail = client.get(f"/admin/activiteiten/{activity.id}?bewerken=1").text
    assert 'name="poster_url"' in detail, "het veld hoort in de bewerkvorm te staan"

    resp = client.post(
        f"/admin/activiteiten/{activity.id}",
        headers=hdr,
        data={
            "name": activity.name,
            "location": "",
            "poster_url": "https://voorbeeld.be/affiche.png",
            "members_only": "",
            "is_cancelled": "",
        },
    )
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    assert db_session.get(Activity, activity.id).poster_url == "https://voorbeeld.be/affiche.png"


def test_de_affiche_zit_in_dezelfde_vorm_als_de_tekstvelden(client, db_session):
    """Eén "Opslaan" voor tekstveld én bestand; geen aparte Uploaden-knop meer."""
    activity, _c, _p = seed_activity_with_product(db_session, is_free=False)
    _login(client)
    detail = client.get(f"/admin/activiteiten/{activity.id}?bewerken=1").text

    assert 'enctype="multipart/form-data"' in detail
    assert 'hx-post="/admin/activiteiten/%d/affiche"' % activity.id not in detail, (
        "de aparte upload-route hoort niet meer in het scherm te staan"
    )


def test_de_bijlage_kan_verwijderd_worden(client, db_session):
    """Ontbrak volledig: een verkeerd bestand kon je alleen overschrijven.

    Since #1559 removing the poster or a component's info attachment is part of
    the fiche's one save: "Verwijderen" marks it, "Opslaan" removes it. The two
    routes that did it on their own are gone."""
    import io

    from app.domains.media.api import MediaAsset
    from tests._fiche import Fiche

    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    activity, comp, _p = seed_activity_with_product(db_session, is_free=False)
    db_session.commit()
    hdr = _login(client)
    fiche = Fiche(db_session, activity.id)
    files = {
        "file": ("affiche.png", io.BytesIO(png), "image/png"),
        f"c.{comp.id}.file": ("info.png", io.BytesIO(png), "image/png"),
    }
    assert fiche.post(client, hdr, files=files).status_code == 200
    assert db_session.query(MediaAsset).count() == 2

    edit = client.get(f"/admin/activiteiten/{activity.id}?bewerken=1").text
    assert 'name="file_delete"' in edit and f'name="c.{comp.id}.info_delete"' in edit
    assert edit.count("data-upload-drop") >= 2, "a remove control beside each attachment"

    fiche = Fiche(db_session, activity.id)
    fiche.data["file_delete"] = "1"
    fiche.set("c", comp.id, info_delete="1")
    assert fiche.post(client, hdr).status_code == 200
    db_session.expire_all()
    assert db_session.query(MediaAsset).count() == 0


def test_de_info_bijlage_heet_niet_meer_reglement(client, db_session):
    """§2.12: één woord voor één ding."""
    activity, comp, _p = seed_activity_with_product(db_session, is_free=False)
    _login(client)
    for suffix in ("", "?bewerken=1"):
        detail = client.get(f"/admin/activiteiten/{activity.id}{suffix}").text
        assert "Info-bijlage" in detail
        assert "reglement" not in detail.lower()


# ── #1016: the public description ────────────────────────────────────────────


def test_de_omschrijving_wordt_bewaard_en_kan_weer_leeg(client, db_session):
    """Two or three sentences for the visitor — and the newsletter (#984).

    Broken on purpose: `velden["description"]` moved back inside the
    `exclude_none` dump → clearing the text silently keeps the old one, and the
    second half of this test fails.
    """
    activity, _comp, _product = seed_activity_with_product(db_session)
    hdr = _login(client)

    detail = client.get(f"/admin/activiteiten/{activity.id}?bewerken=1").text
    assert 'name="description"' in detail, "het veld hoort in de bewerkvorm te staan"

    velden = {
        "name": activity.name,
        "location": "",
        "poster_url": "",
        "members_only": "",
        "is_cancelled": "",
    }
    resp = client.post(
        f"/admin/activiteiten/{activity.id}",
        headers=hdr,
        data={**velden, "description": "We proeven acht rums.\nKom op tijd."},
    )
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    assert db_session.get(Activity, activity.id).description.startswith("We proeven acht rums.")

    client.post(
        f"/admin/activiteiten/{activity.id}", headers=hdr, data={**velden, "description": "   "}
    )
    db_session.expire_all()
    assert db_session.get(Activity, activity.id).description is None


# `test_de_omschrijving_staat_op_de_publieke_pagina` stond hier (#1016) en is
# weggehaald door #1054: Koen vroeg op 20 september 2026 om de omschrijving van de
# publieke kaart te halen, "overal weg". Het omgekeerde staat nu vastgelegd in
# `test_inschrijfdatum_per_onderdeel.py`, samen met de tegenhanger die bewaakt dat
# het veld zelf blijft bestaan en elders gelezen wordt. De test hierboven — bewaren
# en weer leegmaken — blijft, want dat gedrag verandert niet.

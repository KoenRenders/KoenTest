"""Gedeelde records-lijst-conventies op de admin-lijstschermen (C1, #584).

Vier schermen kregen in #587-#590 dezelfde behandeling als Formulieren (#585) en
Activiteiten (#586): zoeken, filters in de filterbalk, en live filteren via htmx.
Deze tests dekken de invarianten die stilletjes kapot kunnen gaan:

* filtert de zoek/filter écht, of ziet het er alleen naar uit;
* geeft een htmx-verzoek het **fragment** terug (en niet de hele pagina) — dat is
  wat voorkomt dat het zoekveld tijdens het typen vervangen wordt;
* blijft de filterstand staan na een mutatie op de inline bewerkbare schermen;
* zijn de zware editor-assets (Trix) verhuisd naar de editorpagina.
"""
from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.cms.api import CmsPage

HX = {"HX-Request": "true"}


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _pagina(db_session, titel: str, slug: str, gepubliceerd: bool) -> CmsPage:
    p = CmsPage(title=titel, slug=slug, content="", is_published=gepubliceerd)
    db_session.add(p)
    db_session.commit()
    return p


# ── Pagina's (#587) ───────────────────────────────────────────────────────────

def test_paginas_zoeken_op_titel_en_slug(client, db_session):
    _login(client)
    _pagina(db_session, "Clubgeschiedenis", "geschiedenis", True)
    _pagina(db_session, "Contactgegevens", "contact", True)

    op_titel = client.get("/admin/paginas", params={"q": "geschied"})
    assert "Clubgeschiedenis" in op_titel.text and "Contactgegevens" not in op_titel.text

    op_slug = client.get("/admin/paginas", params={"q": "contact"})
    assert "Contactgegevens" in op_slug.text and "Clubgeschiedenis" not in op_slug.text


def test_paginas_statusfilter(client, db_session):
    _login(client)
    _pagina(db_session, "Live pagina", "live", True)
    _pagina(db_session, "Kladpagina", "klad", False)

    concept = client.get("/admin/paginas", params={"status": "draft"})
    assert "Kladpagina" in concept.text and "Live pagina" not in concept.text


def test_paginas_htmx_geeft_enkel_de_kaarten(client, db_session):
    """Het fragment mag geen volledige pagina zijn: anders swapt de filterbalk het
    zoekveld weg terwijl je typt."""
    _login(client)
    _pagina(db_session, "Fragmenttest", "fragment", True)

    fragment = client.get("/admin/paginas", params={"q": "fragment"}, headers=HX)
    assert fragment.status_code == 200
    assert "Fragmenttest" in fragment.text
    assert "<html" not in fragment.text.lower()
    assert 'name="q"' not in fragment.text


def test_trix_staat_op_de_editorpagina_en_niet_op_de_lijst(client, db_session):
    """#520-editor hoort bij de editor: de lijst hoeft geen WYSIWYG te laden."""
    _login(client)
    p = _pagina(db_session, "Met editor", "met-editor", False)

    lijst = client.get("/admin/paginas").text
    editor = client.get(f"/admin/paginas/{p.id}").text
    assert "trix.min.js" not in lijst
    assert "trix.min.js" in editor
    assert "Alle pagina's" in editor          # terugkeerlink


def test_onbestaande_pagina_geeft_404(client):
    _login(client)
    assert client.get("/admin/paginas/999999").status_code == 404


# ── Media (#588) ──────────────────────────────────────────────────────────────

def test_media_zoekt_op_titel_en_behoudt_het_filter_bij_opslaan(client, db_session):
    from app.domains.media.api import MediaAsset

    csrf = _login(client)
    db_session.add_all([
        MediaAsset(kind="sponsor", title="Bakkerij Jan", data=b"png",
                   content_type="image/png", byte_size=3, sort_order=0),
        MediaAsset(kind="sponsor", title="Garage Piet", data=b"png",
                   content_type="image/png", byte_size=3, sort_order=1),
    ])
    db_session.commit()
    bakkerij = db_session.query(MediaAsset).filter(MediaAsset.title == "Bakkerij Jan").one()

    gezocht = client.get("/admin/media", params={"q": "bakkerij"})
    assert "Bakkerij Jan" in gezocht.text and "Garage Piet" not in gezocht.text

    # Opslaan vanuit een gefilterde lijst mag niet terugvallen op 'alles'.
    opgeslagen = client.post(f"/admin/media/{bakkerij.id}",
                             data={"kind": "sponsor", "title": "Bakkerij Jan",
                                   "sort_order": "0", "is_active": "1", "q": "bakkerij"},
                             headers={"X-CSRF-Token": csrf})
    assert opgeslagen.status_code == 200
    assert "Bakkerij Jan" in opgeslagen.text and "Garage Piet" not in opgeslagen.text


# ── Gebruikers (#589) ─────────────────────────────────────────────────────────

def test_gebruikers_zoeken_en_rolfilter(client, db_session):
    csrf = _login(client)
    for adres, rollen in (("penning@example.com", ["FINANCE"]),
                          ("helper@example.com", ["OPERATOR"])):
        client.post("/admin/gebruikers", data={"email": adres, "role_codes": rollen},
                    headers={"X-CSRF-Token": csrf})

    gezocht = client.get("/admin/gebruikers", params={"q": "penning"})
    assert "penning@example.com" in gezocht.text
    assert "helper@example.com" not in gezocht.text

    op_rol = client.get("/admin/gebruikers", params={"rol": "OPERATOR"})
    assert "helper@example.com" in op_rol.text
    assert "penning@example.com" not in op_rol.text


def test_gebruikers_actieffilter_en_htmx_fragment(client, db_session):
    from app.domains.auth.models import User

    _login(client)
    db_session.add(User(email="slaper@example.com", is_active=False))
    db_session.commit()

    inactief = client.get("/admin/gebruikers", params={"actief": "nee"})
    assert "slaper@example.com" in inactief.text

    # In het fragment staan enkel de kaarten: de ingelogde (actieve) beheerder
    # hoort er niet in, en het zoekveld evenmin — dat blijft op de pagina staan.
    fragment = client.get("/admin/gebruikers", params={"actief": "nee"}, headers=HX)
    assert "<html" not in fragment.text.lower()
    assert "slaper@example.com" in fragment.text
    assert SEEDED_ADMIN_EMAIL not in fragment.text
    assert 'type="search"' not in fragment.text
    # de filterstand reist wél mee als verborgen veld, zodat opslaan niet ontfiltert
    assert 'name="actief" value="nee"' in fragment.text


# ── Wijzigingen (#590) ────────────────────────────────────────────────────────

def test_wijzigingen_heeft_geen_toon_knop_meer_en_filtert_live(client):
    _login(client)
    pagina = client.get("/admin/ledenwijzigingen")
    assert pagina.status_code == 200
    assert ">Toon<" not in pagina.text
    # actor is het zoekveld geworden, met de kit-debounce van de filterbalk
    assert 'type="search"' in pagina.text and 'name="actor"' in pagina.text
    assert "delay:" in pagina.text
    assert "/admin/ledenwijzigingen/export" in pagina.text

    fragment = client.get("/admin/ledenwijzigingen",
                          params={"actor": "niemand@example.com"}, headers=HX)
    assert fragment.status_code == 200
    assert "<html" not in fragment.text.lower()
    assert "Audit-logboek" in fragment.text          # de lijst zelf komt terug
    assert 'type="search"' not in fragment.text      # het zoekveld blijft staan


# ── Tenants (#584-rest) ───────────────────────────────────────────────────────

def test_tenants_knop_is_primair_en_htmx_geeft_het_fragment(client):
    _login(client)
    pagina = client.get("/admin/tenants")
    assert pagina.status_code == 200
    # primaire knop = merkblauw gevuld; de outline-variant is de secundaire
    knop = pagina.text.split("+ Nieuwe tenant")[0]
    assert "bg-blue-700" in knop.rsplit("<button", 1)[-1]

    fragment = client.get("/admin/tenants", params={"q": "raak"}, headers=HX)
    assert "<html" not in fragment.text.lower()
    assert "+ Nieuwe tenant" not in fragment.text

"""#745 — de volgorde van CMS-pagina's zet je met pijltjes, niet met een getal.

Je moest in élke pagina een nummer typen: om er één omhoog te zetten moest je weten
welk nummer de pagina erboven droeg, beide editors openen en er een getal tussen
verzinnen. Op HDEV stond er daardoor een op **-1** — iemand had geen ruimte meer.

**Twee tests dekken de manieren waarop dit stil misgaat**, en die zijn belangrijker
dan de pijltjes zelf:

* een verplaatsing met een filter aan mag de pagina's búiten dat filter niet
  verzetten. `move_sibling()` hernummert naar 0..n over wat het krijgt, dus voed je
  het de gefilterde rijen, dan herschrijft een filter de volgorde van de hele site;
* een gewone opslag mag `sort_order` niet aanraken. Het getalveld is uit de editor
  weg, dus de sleutel komt niet meer mee — en "niet meegestuurd" is iets anders dan
  "op nul gezet".

`sort_order` bepaalt óók het publieke menu, dus daar staat een aparte test op:
herschik je hier, dan verzet je wat de bezoeker ziet. Dat is de bedoeling, en juist
daarom moet het bewezen zijn.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (lokaal):
  * `verplaats_pagina` gevoed met de gefilterde lijst i.p.v. `list_pages(db)` → de
    filtertest valt om en de andere blijven groen;
  * `sort_order: str | None = Form(None)` terug op `Form("0")` → de opslagtest valt
    om, precies met de stille regressie die ze beschrijft.
"""
import pytest

from app.domains.cms.models import CmsPage
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return {"X-CSRF-Token": csrf_token_for(waarde), "HX-Request": "true"}


def _paginas(db, *specs) -> list[CmsPage]:
    """Maakt pagina's aan met de gegeven (slug, sort_order); de rest staat vast."""
    gemaakt = []
    for slug, volgorde in specs:
        pagina = CmsPage(slug=slug, title=slug.title(), content="<p>x</p>",
                         is_published=True, show_in_nav=True, sort_order=volgorde)
        db.add(pagina)
        gemaakt.append(pagina)
    db.flush()
    return gemaakt


def _volgorde(db, slugs) -> list[str]:
    from app.domains.cms.api import list_pages

    return [p.slug for p in list_pages(db) if p.slug in slugs]


# ── De pijltjes ──────────────────────────────────────────────────────────────

def test_omhoog_wisselt_met_de_buur(client, db_session):
    slugs = ("aaa", "bbb", "ccc")
    _paginas(db_session, ("aaa", 10), ("bbb", 11), ("ccc", 12))
    bbb = db_session.query(CmsPage).filter(CmsPage.slug == "bbb").one()
    hdr = _login(client)

    resp = client.post(f"/admin/paginas/{bbb.id}/volgorde/omhoog", headers=hdr)

    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    assert _volgorde(db_session, slugs) == ["bbb", "aaa", "ccc"]


def test_dubbels_en_negatieve_waarden_worden_genormaliseerd(client, db_session):
    """Het geval dat vandaag écht bestaat: alles op 0, en eentje op -1."""
    slugs = ("een", "twee", "drie")
    _paginas(db_session, ("een", 0), ("twee", 0), ("drie", -1))
    twee = db_session.query(CmsPage).filter(CmsPage.slug == "twee").one()
    hdr = _login(client)

    client.post(f"/admin/paginas/{twee.id}/volgorde/omhoog", headers=hdr)

    db_session.expire_all()
    # Alleen deze drie: de migraties seeden per tenant hun eigen pagina's, en
    # `list_pages` is tenant-gebonden — over alle tenants heen tellen zou iets anders
    # meten dan wat de verplaatsing aanraakt.
    waarden = [p.sort_order for p in db_session.query(CmsPage)
               .filter(CmsPage.slug.in_(slugs)).order_by(CmsPage.sort_order).all()]
    assert len(set(waarden)) == len(waarden), f"er staan nog dubbels: {waarden}"
    assert all(v >= 0 for v in waarden), f"er staat nog een negatieve waarde: {waarden}"
    # Beginstand: een=0, twee=0, drie=-1. Genormaliseerd op (sort_order, id) wordt
    # dat drie, een, twee — de -1 gaat vooraan, de twee nullen houden hun id-volgorde.
    # "twee" één omhoog wisselt dan met "een".
    assert _volgorde(db_session, slugs) == ["drie", "twee", "een"], (
        "de verplaatsing zelf klopt niet")


# ── De twee manieren waarop dit stil misgaat ─────────────────────────────────

def test_een_filter_verzet_de_paginas_erbuiten_niet(client, db_session):
    """De belangrijkste test van dit issue.

    Met een filter aan zie je maar een deel van de lijst. Zou de verplaatsing over
    díe rijen hernummeren, dan krijgen ze 0..n en verliezen alle andere pagina's hun
    plaats — een filter herschrijft dan de volgorde van de hele site.
    """
    _paginas(db_session, ("zichtbaar-a", 20), ("verborgen-b", 21),
             ("zichtbaar-c", 22), ("verborgen-d", 23))
    c = db_session.query(CmsPage).filter(CmsPage.slug == "zichtbaar-c").one()
    hdr = _login(client)

    # De filterstand reist mee zoals de browser hem meestuurt (#671).
    resp = client.post(f"/admin/paginas/{c.id}/volgorde/omhoog",
                       headers={**hdr, "HX-Current-URL": "/admin/paginas?q=zichtbaar"})
    assert resp.status_code == 200, resp.text

    db_session.expire_all()
    alles = _volgorde(db_session, ("zichtbaar-a", "verborgen-b", "zichtbaar-c",
                                   "verborgen-d"))
    # c gaat één plaats omhoog binnen de VOLLEDIGE lijst: over verborgen-b heen.
    assert alles == ["zichtbaar-a", "zichtbaar-c", "verborgen-b", "verborgen-d"], (
        "de pagina's buiten het filter zijn verzet")


def test_een_gewone_opslag_laat_de_volgorde_met_rust(client, db_session):
    """Het getalveld is weg, dus de sleutel komt niet meer mee.

    Zou `sort_order` dan op 0 terugvallen, dan wist een gewone opslag de volgorde die
    je net met de pijltjes zette — en dat merk je pas als het menu door elkaar staat.
    """
    _paginas(db_session, ("blijft", 7))
    pagina = db_session.query(CmsPage).filter(CmsPage.slug == "blijft").one()
    hdr = _login(client)

    resp = client.post(f"/admin/paginas/{pagina.id}", headers=hdr, data={
        "title": "Nieuwe titel", "slug": "blijft", "content": "<p>x</p>",
        "is_published": "1"})

    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    bewaard = db_session.get(CmsPage, pagina.id)
    assert bewaard.title == "Nieuwe titel", "de opslag zelf werkte niet"
    assert bewaard.sort_order == 7, "een gewone opslag heeft de volgorde gewist"


# ── Het publieke menu volgt ──────────────────────────────────────────────────

def test_de_publieke_navigatie_volgt_de_nieuwe_volgorde(client, db_session):
    """Herschikken in het beheer verzet wat de bezoeker ziet. Zonder deze test
    herschik je een beheerlijstje en liegt het scherm over de site."""
    _paginas(db_session, ("menu-een", 30), ("menu-twee", 31))
    twee = db_session.query(CmsPage).filter(CmsPage.slug == "menu-twee").one()
    hdr = _login(client)

    voor = client.get("/").text
    assert voor.index("/menu-een") < voor.index("/menu-twee")

    client.post(f"/admin/paginas/{twee.id}/volgorde/omhoog", headers=hdr)

    na = client.get("/").text
    assert na.index("/menu-twee") < na.index("/menu-een"), (
        "het publieke menu volgt de nieuwe volgorde niet")


def test_het_getalveld_staat_niet_meer_in_de_editor(client, db_session):
    """Twee bedieningen voor hetzelfde ding kunnen elkaar tegenspreken."""
    _paginas(db_session, ("editorcheck", 3))
    pagina = db_session.query(CmsPage).filter(CmsPage.slug == "editorcheck").one()
    hdr = _login(client)

    html = client.get(f"/admin/paginas/{pagina.id}", headers=hdr).text

    assert 'name="sort_order"' not in html

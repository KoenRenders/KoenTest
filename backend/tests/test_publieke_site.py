"""React-exit 405-a: publieke site-kern — homepage, word-lid, CMS-slugs,
betaalpagina's (server-rendered)."""
from app.domains.cms.models import CmsPage
from tests.conftest import seed_postal_code


def test_homepage_renders_with_intro_and_activities(client, db_session):
    intro = db_session.query(CmsPage).filter(CmsPage.slug == "home-intro").first()
    if intro is None:
        intro = CmsPage(slug="home-intro", title="Intro", is_published=False)
        db_session.add(intro)
    intro.content = "<p>Welkom bij Raak!</p>"
    db_session.flush()
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Welkom bij Raak" in resp.text and "Word lid" in resp.text
    assert "Activiteiten" in resp.text


def test_cms_slug_pagina(client, db_session):
    db_session.add(CmsPage(slug="over-ons", title="Over ons",
                           content="<p>Raak is een vereniging.</p>", is_published=True))
    db_session.flush()
    resp = client.get("/over-ons")
    assert resp.status_code == 200 and "Raak is een vereniging" in resp.text
    assert client.get("/bestaat-niet").status_code == 404


def test_betaling_resultaat_paginas(client, db_session):
    ok = client.get("/betaling/succes")
    assert ok.status_code == 200 and "Betaling ontvangen" in ok.text
    nok = client.get("/betaling/geannuleerd")
    assert nok.status_code == 200 and "geannuleerd" in nok.text


def test_lid_worden_formulier_en_registratie(client, db_session, mock_mollie):
    seed_postal_code(db_session, code="2400", municipality="Mol")
    page = client.get("/lid-worden")
    assert page.status_code == 200 and "Hoofdlid" in page.text and "Postcode" in page.text

    rij = client.get("/lid-worden/persoon-rij?index=1")
    assert rij.status_code == 200 and "Gezinslid 2" in rij.text

    resp = client.post("/lid-worden", data={
        "m0_first_name": "An", "m0_last_name": "Peeters",
        "m0_email": "an@example.com", "m0_mobile": "0470000000",
        "m0_relation_type": "HOOFDLID",
        "m1_first_name": "Bart", "m1_last_name": "Peeters",
        "m1_relation_type": "PARTNER",
        "street": "Dorpsstraat", "house_number": "1", "postal_code": "2400",
        "payment_method": "online",
    })
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect", "").startswith("https://mollie.test/checkout/")

    from app.domains.mdm.api import Person
    namen = {p.first_name for p in db_session.query(Person).all()}
    assert {"An", "Bart"} <= namen


def test_lid_worden_validatiefout_toont_banner(client, db_session):
    seed_postal_code(db_session, code="2400", municipality="Mol")
    resp = client.post("/lid-worden", data={
        "m0_first_name": "Zonder", "m0_last_name": "Mail",
        "m0_relation_type": "HOOFDLID",
        "street": "X", "house_number": "1", "postal_code": "2400",
        "payment_method": "online",
    })
    assert resp.status_code == 200 and "verplicht" in resp.text.lower()

"""React-exit 405-a: publieke site-kern — homepage, word-lid, CMS-slugs,
betaalpagina's (server-rendered)."""

import re

from app.domains.cms.models import CmsPage
from tests.conftest import seed_postal_code, signup_fields


def test_homepage_renders_with_intro_and_activities(client, db_session):
    # Sinds #727 geldt `is_published` ook voor dit blok. Alle rijen met deze slug:
    # de migraties seeden er één per tenant en het verzoek kiest de zijne (zie
    # test_siteblokken_publicatie.py, waar de tegenproef staat).
    intros = db_session.query(CmsPage).filter(CmsPage.slug == "home-intro").all()
    if not intros:
        intros = [CmsPage(slug="home-intro", title="Intro")]
        db_session.add(intros[0])
    # CR-17 (#1671): de site toont het GEPUBLICEERDE DOCUMENT, dus schrijft
    # deze test de intro zoals een redacteur dat doet: door de deuren van de
    # app — Opslaan, Publiceren. `intro.content` overschrijven toetst niets
    # meer: de lezer kijkt er niet meer naar.
    from app.domains.cms.api import publish, save_document

    for intro in intros:
        intro.is_published = True
        save_document(
            db_session,
            intro.id,
            {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "Welkom bij Raak!"}]}
                ],
            },
        )
        publish(db_session, intro.id)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Welkom bij Raak" in resp.text and "Word lid" in resp.text
    assert "Activiteiten" in resp.text


def test_cms_slug_pagina(client, db_session):
    db_session.add(
        CmsPage(
            slug="over-ons",
            title="Over ons",
            content="<p>Raak is een vereniging.</p>",
            is_published=True,
        )
    )
    db_session.flush()
    resp = client.get("/over-ons")
    assert resp.status_code == 200 and "Raak is een vereniging" in resp.text
    assert client.get("/bestaat-niet").status_code == 404


def test_betaling_resultaat_paginas(client, db_session):
    ok = client.get("/betaling/succes")
    # #1589: a received payment is reported only when the provider confirmed it
    # (`test_payment_return_page.py`); without a reference the page claims nothing.
    assert ok.status_code == 200 and "Je betaling wordt verwerkt" in ok.text
    assert "Betaling ontvangen" not in ok.text
    nok = client.get("/betaling/geannuleerd")
    assert nok.status_code == 200 and "geannuleerd" in nok.text


PARTNER = {
    "first_name": "Bart",
    "last_name": "Peeters",
    "relation_type": "PARTNER",
    # #551: bijkomend lid vereist geboortedatum + geslacht.
    "date_of_birth": "2010-05-05",
    "gender_code": "M",
}
HEAD = {
    "h.n0.first_name": "An",
    "h.n0.last_name": "Peeters",
    "h.n0.gender_code": "F",
    "address.street": "Dorpsstraat",
    "address.house_number": "1",
}


def _refused_places(resp) -> list[str]:
    """A refused Word lid form (#1590): the banner alone for the page's message
    line, and the form's names of the fields it refuses."""
    assert resp.status_code == 422, resp.text[:300]
    assert resp.headers["HX-Retarget"] == "#lid-worden-melding"
    assert "<html" not in resp.text.lower(), "the page came back instead of the banner"
    assert "Verzenden kan nog niet" in resp.text
    return re.findall(r'data-error-for="([^"]+)"', resp.text)


def test_lid_worden_formulier_en_registratie(client, db_session, mock_mollie):
    seed_postal_code(db_session, code="2400", municipality="Mol")
    page = client.get("/lid-worden")
    assert page.status_code == 200 and "Hoofdlid" in page.text and "Postcode" in page.text
    # The row "+ Gezinslid toevoegen" adds stands in the page (the group's template).
    assert "Gezinslid toevoegen" in page.text and 'name="h.__H__.first_name"' in page.text

    resp = client.post(
        "/lid-worden",
        data=signup_fields(
            None, PARTNER, emails=("an@example.com",), payment_method="online", **HEAD
        ),
    )
    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect", "").startswith("https://mollie.test/checkout/")
    # The page reports while the browser leaves for the provider.
    assert "Je aanvraag is ontvangen" in resp.text and "data-signup-checkout" in resp.text
    assert 'id="lid-worden-form"' not in resp.text

    from app.domains.mdm.api import Person

    namen = {p.first_name for p in db_session.query(Person).all()}
    assert {"An", "Bart"} <= namen


def test_lid_worden_via_overschrijving_meldt_de_ontvangst(client, db_session):
    """The other payment choice: no redirect, and the page says the payment
    details follow by e-mail."""
    seed_postal_code(db_session, code="2400", municipality="Mol")
    resp = client.post("/lid-worden", data=signup_fields(None, emails=("an@example.com",), **HEAD))
    assert resp.status_code == 200
    assert "HX-Redirect" not in resp.headers
    assert "Je aanvraag is ontvangen" in resp.text and "data-payment-pending" in resp.text
    assert "data-signup-checkout" not in resp.text and 'id="lid-worden-form"' not in resp.text


def test_bijkomend_lid_vereist_dob_en_geslacht(client, db_session):
    """#551: een bijkomend gezinslid (niet-hoofdlid) zonder geboortedatum of
    geslacht wordt server-side geweigerd, met een foutbanner — at that person's
    own field. The main member is complete, so only the extra person can be the
    cause (#681); the same form with the two fields is accepted above."""
    from app.domains.mdm.api import Person

    seed_postal_code(db_session, code="2400", municipality="Mol")
    partner = {**PARTNER, "date_of_birth": "", "gender_code": None}
    resp = client.post(
        "/lid-worden",
        data=signup_fields(
            None, partner, emails=("an@example.com",), payment_method="online", **HEAD
        ),
    )
    assert _refused_places(resp) == ["h.n1.date_of_birth"]
    assert "verplicht" in resp.text.lower()
    assert not db_session.query(Person).filter(Person.last_name == "Peeters").all()


def test_lid_worden_validatiefout_toont_banner(client, db_session):
    """The main member without an e-mail address: refused at the e-mail row."""
    seed_postal_code(db_session, code="2400", municipality="Mol")
    resp = client.post(
        "/lid-worden",
        data=signup_fields(
            None,
            emails=("",),
            payment_method="online",
            **{"h.n0.first_name": "Zonder", "h.n0.last_name": "Mail", "h.n0.mobile": ""},
        ),
    )
    assert _refused_places(resp) == ["e.n0e.value", "h.n0.mobile"]
    assert "E-mailadres is verplicht voor het hoofdgezinslid." in resp.text


def test_lid_worden_weigert_een_leeg_adres_en_een_ontbrekende_betaalwijze(client, db_session):
    """New with #1590: an empty street or house number and a missing payment
    method are refused as fields, together with the postal code."""
    seed_postal_code(db_session, code="2400", municipality="Mol")
    resp = client.post(
        "/lid-worden",
        data=signup_fields(
            None,
            emails=("an@example.com",),
            payment_method=None,
            **{
                **HEAD,
                "address.street": " ",
                "address.house_number": "",
                "address.postal_code": "",
            },
        ),
    )
    assert _refused_places(resp) == [
        "address.postal_code",
        "address.street",
        "address.house_number",
        "payment_method",
    ]


def test_lid_worden_weigert_een_gezin_dat_al_bestaat_in_de_banner(client, db_session):
    """What the service refuses has no field: it stands in the banner as a
    sentence, and the form stays. Here the same household sent twice."""
    seed_postal_code(db_session, code="2400", municipality="Mol")
    form = signup_fields(None, emails=("an@example.com",), **HEAD)
    assert client.post("/lid-worden", data=form).status_code == 200

    resp = client.post("/lid-worden", data=form)
    assert resp.status_code == 422, resp.text[:300]
    assert resp.headers["HX-Retarget"] == "#lid-worden-melding"
    assert "<html" not in resp.text.lower()
    assert "Verzenden is niet gelukt." in resp.text
    assert "data-error-for" not in resp.text

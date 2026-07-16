"""Fase 2b (#400): server-rendered ledenbeheer (htmx) — lijst, detail, mutaties
en de import-wizard (sessie + CSRF, zelfde patroon als werkbank/e-maillog)."""
from tests.conftest import (
    SEEDED_ADMIN_EMAIL, create_test_family, seed_postal_code,
)
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Address, ContactDetail, Person


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _family_with_address(db):
    member, person = create_test_family(db, email="ui-lid@example.com")
    pc = seed_postal_code(db, code="2400", municipality="Mol")
    db.add(Address(person_id=person.id, street="Dorpsstraat", house_number="1",
                   postal_code_id=pc.id))
    db.flush()
    return member, person


def test_leden_page_requires_session(client):
    assert client.get("/admin/leden").status_code == 401


def test_leden_lijst_and_detail(client, db_session):
    member, person = _family_with_address(db_session)
    _login(client)

    page = client.get("/admin/leden")
    assert page.status_code == 200 and "Persoon" in page.text

    lijst = client.get("/admin/leden/lijst?q=Persoon")
    assert lijst.status_code == 200 and "Dorpsstraat" in lijst.text

    detail = client.get(f"/admin/leden/gezin/{member.id}")
    assert detail.status_code == 200
    assert "Dorpsstraat 1" in detail.text and "Lidmaatschappen" in detail.text


def test_persoon_bewerken_via_scherm(client, db_session):
    member, person = _family_with_address(db_session)
    csrf = _login(client)

    resp = client.post(f"/admin/leden/gezin/{member.id}/persoon/{person.id}",
                       data={"first_name": "Nieuw", "last_name": "Naam",
                             "contact_email": "nieuw@example.com",
                             "mobile": "0470000000"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "Nieuw Naam" in resp.text
    db_session.expire_all()
    assert db_session.get(Person, person.id).first_name == "Nieuw"
    mails = [c.value for c in db_session.query(ContactDetail)
             .filter(ContactDetail.person_id == person.id,
                     ContactDetail.contact_type_code == "EMAIL").all()]
    assert "nieuw@example.com" in mails


def test_mutatie_zonder_csrf_geweigerd(client, db_session):
    member, person = _family_with_address(db_session)
    _login(client)
    resp = client.post(f"/admin/leden/gezin/{member.id}/persoon/{person.id}",
                       data={"first_name": "X", "last_name": "Y"})
    assert resp.status_code == 403


def test_lidmaatschap_toevoegen_en_verwijderen(client, db_session):
    member, _person = _family_with_address(db_session)
    csrf = _login(client)

    resp = client.post(f"/admin/leden/gezin/{member.id}/lidmaatschappen",
                       data={"year": "2031"}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and "2031" in resp.text

    from app.domains.membership.api import Membership
    ms = (db_session.query(Membership)
          .filter(Membership.member_id == member.id, Membership.year == 2031).one())
    weg = client.post(f"/admin/leden/gezin/{member.id}/lidmaatschappen/{ms.id}/verwijderen",
                      headers={"X-CSRF-Token": csrf})
    assert weg.status_code == 200 and "2031" not in weg.text


def test_leden_page_links_to_import(client):
    """Regressie: de importwizard (/admin/leden-import) bestond wél maar was
    onbereikbaar — geen enkele link of nav-item wees ernaar, dus de facto 'weg'.
    De Leden-pagina moet er nu naartoe linken (ingang voor de import)."""
    _login(client)
    page = client.get("/admin/leden")
    assert page.status_code == 200
    assert "/admin/leden-import" in page.text


def test_import_wizard_page_and_bad_file(client):
    _login(client)
    page = client.get("/admin/leden-import")
    assert page.status_code == 200 and "Controleer bestand" in page.text

    csrf = _login(client)
    resp = client.post("/admin/leden-import/preview",
                       files={"file": ("leden.xlsx", b"nep", "application/octet-stream")},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200 and ".xlsx" in resp.text  # nette foutbanner

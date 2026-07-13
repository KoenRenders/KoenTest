"""Export/overzicht van ledendata-wijzigingen sinds een datum (#82)."""
from datetime import date, timedelta
from io import BytesIO

from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.teletype import extractText

from tests.conftest import seed_postal_code


def _family_payload(email="lid@example.com"):
    return {
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [{
            "last_name": "Janssens", "first_name": "An", "email": email,
            "mobile": "0470123456", "relation_type": "HOOFDLID",
        }],
    }


def _create_family(client, db_session):
    seed_postal_code(db_session)
    resp = client.post("/api/v1/families", json=_family_payload())
    assert resp.status_code == 201, resp.text


def test_member_changes_requires_admin(client):
    resp = client.get("/api/v1/admin/member-changes", params={"since": date.today().isoformat()})
    assert resp.status_code in (401, 403)


def test_member_changes_lists_recent_changes(client, db_session, admin_headers):
    _create_family(client, db_session)
    resp = client.get("/api/v1/admin/member-changes",
                      params={"since": date.today().isoformat()}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    entities = {r["entity"] for r in rows}
    # Een gezinsregistratie raakt minstens persoon, gezin, gezinslid en contact.
    assert {"Persoon", "Gezin", "Gezinslid"}.issubset(entities)
    person_row = next(r for r in rows if r["entity"] == "Persoon")
    assert person_row["operation_label"] == "Toegevoegd"
    assert "An" in person_row["summary"]


def test_change_summaries_have_no_raw_ids(client, db_session, admin_headers):
    """De Details-kolom toont geen nietszeggende #ID's meer; een adres toont de
    gemeente i.p.v. een postcode-id."""
    _create_family(client, db_session)
    rows = client.get("/api/v1/admin/member-changes",
                      params={"since": date.today().isoformat()}, headers=admin_headers).json()
    summaries = " | ".join(r["summary"] for r in rows)
    assert "persoon #" not in summaries
    assert "gezin #" not in summaries
    assert "postcode-id" not in summaries
    adres = next(r for r in rows if r["entity"] == "Adres")
    assert "2400 Mol" in adres["summary"]


def test_member_changes_respects_since_date(client, db_session, admin_headers):
    _create_family(client, db_session)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.get("/api/v1/admin/member-changes",
                      params={"since": tomorrow}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_member_changes_ods_export(client, db_session, admin_headers):
    _create_family(client, db_session)
    resp = client.get("/api/v1/admin/member-changes/export",
                      params={"since": date.today().isoformat()}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert "opendocument.spreadsheet" in resp.headers.get("content-type", "")
    table = load(BytesIO(resp.content)).getElementsByType(Table)[0]
    trs = table.getElementsByType(TableRow)
    headers = [extractText(tc) for tc in trs[0].getElementsByType(TableCell)]
    assert headers[0] == "Tijdstip" and "Details" in headers
    # Nieuwe kolommen: naam + hoofdlid-adres (scherm + export) en externe ID's (export).
    for col in ("Naam persoon", "Adres hoofdlid", "Externe ID persoon", "Externe ID hoofdlid"):
        assert col in headers, headers
    assert len(trs) >= 2  # kop + minstens één wijziging


def test_member_changes_enriched_with_person_and_head(client, db_session, admin_headers):
    """Elke ledenwijziging draagt de naam van de persoon, het hoofdlid-adres en
    (in de feed/export) de externe ID's van persoon en hoofdlid."""
    _create_family(client, db_session)
    # Geef het hoofdlid een extern lidnummer (Raak Nationaal).
    from app.domains.mdm.api import Person
    from app.domains.mdm.api import ExternalNumber
    person = db_session.query(Person).filter(Person.first_name == "An").first()
    db_session.add(ExternalNumber(person_id=person.id, source="ledenadministratie",
                                  external_id="RN-12345"))
    db_session.flush()

    resp = client.get("/api/v1/admin/member-changes",
                      params={"since": date.today().isoformat()}, headers=admin_headers)
    rows = resp.json()
    person_row = next(r for r in rows if r["entity"] == "Persoon")
    assert person_row["person_name"] == "An Janssens"
    assert person_row["head_address"] == "Milostraat 40, 2400 Mol"
    assert person_row["person_external_id"] == "RN-12345"
    assert person_row["head_external_id"] == "RN-12345"  # An is zelf het hoofdlid

    # En het gezin/lidmaatschap-rij (enkel member_id) valt terug op het hoofdlid.
    gezin_row = next(r for r in rows if r["entity"] == "Gezin")
    assert gezin_row["person_name"] == "An Janssens"
    assert gezin_row["head_address"] == "Milostraat 40, 2400 Mol"


def test_changes_feed_enriches_payment_with_registration_person(client, db_session, admin_headers):
    """Een betaling/bestelregel hangt aan een inschrijving → de feed toont de
    persoon + hoofdlid-adres van die inschrijving (niet langer '—')."""
    from tests.conftest import seed_activity_with_product
    from app.domains.mdm.api import Person
    from app.domains.mdm.api import ExternalNumber
    from app.domains.activities.api import Registration

    _create_family(client, db_session)  # An Janssens, hoofdlid, Milostraat 40 2400 Mol
    person = db_session.query(Person).filter(Person.first_name == "An").first()
    db_session.add(ExternalNumber(person_id=person.id, source="ledenadministratie", external_id="RN-1"))

    _, comp, product = seed_activity_with_product(db_session, price="2.00")
    reg_resp = client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        "contact_name": "Gast X", "contact_email": "gast@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert reg_resp.status_code in (200, 201), reg_resp.text

    # Koppel de inschrijving aan het lid (member-registratie).
    reg = db_session.query(Registration).order_by(Registration.id.desc()).first()
    reg.person_id = person.id
    db_session.flush()

    resp = client.get("/api/v1/admin/changes",
                      params={"since": date.today().isoformat(), "group": "Betalingen"},
                      headers=admin_headers)
    pay = next(r for r in resp.json()["rows"] if r["entity"] == "Betaling")
    assert pay["person_name"] == "An Janssens"
    assert pay["head_address"] == "Milostraat 40, 2400 Mol"


def test_changes_feed_matches_guest_payment_by_email(client, db_session, admin_headers):
    """Een gast-inschrijving (geen person_id) waarvan het contact-e-mailadres een lid
    is, toont tóch de persoon + hoofdlid-adres via de e-mailmatch (#221)."""
    from tests.conftest import seed_activity_with_product
    from app.domains.mdm.api import Person
    from app.domains.mdm.api import ExternalNumber

    _create_family(client, db_session)  # An Janssens, e-mail lid@example.com, Milostraat 40 2400 Mol
    person = db_session.query(Person).filter(Person.first_name == "An").first()
    db_session.add(ExternalNumber(person_id=person.id, source="ledenadministratie", external_id="RN-9"))
    db_session.flush()

    _, comp, product = seed_activity_with_product(db_session, price="2.00")
    reg_resp = client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        "contact_name": "Gast Naam", "contact_email": "lid@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert reg_resp.status_code in (200, 201), reg_resp.text

    resp = client.get("/api/v1/admin/changes",
                      params={"since": date.today().isoformat(), "group": "Betalingen"},
                      headers=admin_headers)
    pay = next(r for r in resp.json()["rows"] if r["entity"] == "Betaling")
    # An is zelf het hoofdlid → persoon- en hoofdlid-kolommen wijzen naar haar.
    assert pay["person_name"] == "An Janssens"
    assert pay["person_external_id"] == "RN-9"
    assert pay["head_address"] == "Milostraat 40, 2400 Mol"
    assert pay["head_external_id"] == "RN-9"


def test_changes_feed_person_and_head_columns_differ(client, db_session, admin_headers):
    """Persoon én hoofdlid worden los ingevuld (#221): een gezinslid (kind) inschrijven
    toont naam + extern nummer van het kind als persoon, maar adres + extern nummer van
    het hoofdlid."""
    from tests.conftest import seed_activity_with_product
    from app.domains.mdm.api import Person, MemberPerson
    from app.domains.mdm.api import ExternalNumber
    from app.domains.mdm.api import ContactDetail

    _create_family(client, db_session)  # hoofdlid An Janssens, Milostraat 40 2400 Mol
    an = db_session.query(Person).filter(Person.first_name == "An").first()
    db_session.add(ExternalNumber(person_id=an.id, source="ledenadministratie", external_id="RN-HEAD"))
    member_id = db_session.query(MemberPerson).filter(MemberPerson.person_id == an.id).first().member_id

    # Kind toevoegen aan hetzelfde gezin: eigen e-mail + extern nummer, geen eigen adres.
    kind = Person(first_name="Tom", last_name="Janssens")
    db_session.add(kind)
    db_session.flush()
    db_session.add(MemberPerson(member_id=member_id, person_id=kind.id, relation_type="KIND"))
    db_session.add(ContactDetail(person_id=kind.id, contact_type_code="EMAIL", value="tom@example.com"))
    db_session.add(ExternalNumber(person_id=kind.id, source="ledenadministratie", external_id="RN-KIND"))
    db_session.flush()

    _, comp, product = seed_activity_with_product(db_session, price="2.00")
    reg_resp = client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        "contact_name": "Tom", "contact_email": "tom@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert reg_resp.status_code in (200, 201), reg_resp.text

    rows = client.get("/api/v1/admin/changes",
                      params={"since": date.today().isoformat(), "group": "Betalingen"},
                      headers=admin_headers).json()["rows"]
    pay = next(r for r in rows if r["entity"] == "Betaling")
    # Persoon = het kind:
    assert pay["person_name"] == "Tom Janssens"
    assert pay["person_external_id"] == "RN-KIND"
    # Hoofdlid = An, met háár adres en extern nummer:
    assert pay["head_address"] == "Milostraat 40, 2400 Mol"
    assert pay["head_external_id"] == "RN-HEAD"


def test_changes_feed_payment_guest_shows_contact_name(client, db_session):
    """Een gast-inschrijving zonder gekoppeld lid toont de contactnaam, geen gezin."""
    from tests.conftest import seed_activity_with_product, seed_postal_code
    seed_postal_code(db_session)
    _, comp, product = seed_activity_with_product(db_session, price="2.00")
    reg_resp = client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        "contact_name": "Gast Zonderlid", "contact_email": "gast2@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert reg_resp.status_code in (200, 201), reg_resp.text

    from app.domains.auth.api import create_access_token
    headers = {"Authorization": f"Bearer {create_access_token({'sub': 'koen.renders@gmail.com'})}"}
    resp = client.get("/api/v1/admin/changes",
                      params={"since": date.today().isoformat(), "group": "Betalingen"},
                      headers=headers)
    pay = next(r for r in resp.json()["rows"] if r["entity"] == "Betaling")
    assert pay["person_name"] == "Gast Zonderlid"
    assert pay["head_address"] == ""

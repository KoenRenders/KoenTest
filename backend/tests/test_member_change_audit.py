"""Ledenwijziging-historie logt enkel wat écht wijzigt (#188).

Een formulier stuurt alle velden mee; onveranderde velden/contacten mogen geen
history-rij maken (anders 3 rijen voor één mobiel-wijziging)."""
from datetime import date

from app.domains.mdm.api import PersonHistory, ContactDetailHistory
from app.domains.mdm.api import Person
from tests.conftest import seed_postal_code


def _make_person(client, db):
    seed_postal_code(db)
    resp = client.post("/api/v1/families", json={
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [{"last_name": "Wiske", "first_name": "Suske",
                     "email": "suske@suske.be", "mobile": "0470111111",
                     "relation_type": "HOOFDLID"}],
    })
    assert resp.status_code == 201, resp.text
    return db.query(Person).order_by(Person.id.desc()).first()


def test_only_changed_contact_is_snapshotted(client, db_session, admin_headers):
    person = _make_person(client, db_session)
    before_contacts = db_session.query(ContactDetailHistory).filter(
        ContactDetailHistory.person_id == person.id).count()
    before_persons = db_session.query(PersonHistory).filter(
        PersonHistory.person_id == person.id).count()

    # Enkel het mobiel nummer wijzigt; e-mail blijft gelijk.
    r = client.put(f"/api/v1/persons/{person.id}/contacts",
                   json={"email": "suske@suske.be", "mobile": "0470222222"},
                   headers=admin_headers)
    assert r.status_code == 200, r.text

    contacts = db_session.query(ContactDetailHistory).filter(
        ContactDetailHistory.person_id == person.id).order_by(ContactDetailHistory.id).all()
    assert len(contacts) - before_contacts == 1          # exact één nieuwe rij
    assert contacts[-1].contact_type_code == "MOBILE"    # en die gaat over MOBILE

    after_persons = db_session.query(PersonHistory).filter(
        PersonHistory.person_id == person.id).count()
    assert after_persons == before_persons               # geen onnodige persoon-rij


def test_contact_change_shows_old_to_new(client, db_session, admin_headers):
    """#188: een gewijzigd contact toont 'oud → nieuw' in de wijzigingen-feed."""
    person = _make_person(client, db_session)
    client.put(f"/api/v1/persons/{person.id}/contacts",
               json={"email": "suske@suske.be", "mobile": "0470222222"}, headers=admin_headers)
    resp = client.get("/api/v1/admin/member-changes",
                      params={"since": date.today().isoformat()}, headers=admin_headers)
    rows = resp.json()
    mobile = [r for r in rows
              if r["entity"] == "Contact" and "MOBILE" in r["summary"] and "→" in r["summary"]]
    assert mobile, rows
    assert "0470111111" in mobile[0]["summary"] and "0470222222" in mobile[0]["summary"]


def test_person_name_change_shows_old_to_new(client, db_session, admin_headers):
    """#188: een naamswijziging toont 'oud → nieuw' in de wijzigingen-feed."""
    person = _make_person(client, db_session)
    r = client.put(f"/api/v1/persons/{person.id}",
                   json={"first_name": "Suske", "last_name": "Vandersteen"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    resp = client.get("/api/v1/admin/member-changes",
                      params={"since": date.today().isoformat()}, headers=admin_headers)
    rows = resp.json()
    naam = [row for row in rows if row["entity"] == "Persoon" and "→" in row["summary"]]
    assert naam, rows
    assert "Suske Wiske" in naam[0]["summary"] and "Suske Vandersteen" in naam[0]["summary"]


def test_person_update_without_change_makes_no_history(client, db_session, admin_headers):
    person = _make_person(client, db_session)
    before = db_session.query(PersonHistory).filter(PersonHistory.person_id == person.id).count()

    # Zelfde naam opnieuw indienen → geen wijziging.
    r = client.put(f"/api/v1/persons/{person.id}",
                   json={"first_name": "Suske", "last_name": "Wiske"}, headers=admin_headers)
    assert r.status_code == 200, r.text

    after = db_session.query(PersonHistory).filter(PersonHistory.person_id == person.id).count()
    assert after == before

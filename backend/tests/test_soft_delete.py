"""Soft delete op het leden-domein (#166): verwijderde rijen worden globaal uit
reads gefilterd maar blijven in de DB; partiële uniciteit laat heraanmaak toe;
de history (en dus de #82-export) toont de verwijdering nog steeds."""
from datetime import date

from app.models.member import Member, Membership, Person
from tests.conftest import seed_postal_code


def _payload(email="lid@example.com"):
    return {
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [{"last_name": "Janssens", "first_name": "An", "email": email,
                     "mobile": "0470123456", "relation_type": "HOOFDLID"}],
    }


def _create_family(client, db, email="lid@example.com"):
    seed_postal_code(db)
    resp = client.post("/api/v1/families", json=_payload(email))
    assert resp.status_code == 201, resp.text
    return db.query(Member).order_by(Member.id.desc()).first()


def test_soft_deleted_family_hidden_but_retained(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    mid = member.id
    assert client.delete(f"/api/v1/families/{mid}", headers=admin_headers).status_code == 204

    # Verborgen voor gewone reads (member + bijhorende rijen).
    assert db_session.query(Member).filter(Member.id == mid).first() is None
    assert db_session.query(Membership).filter(Membership.member_id == mid).first() is None

    # Maar bewaard in de DB met deleted_at (opt-out include_deleted).
    kept = (db_session.query(Member).execution_options(include_deleted=True)
            .filter(Member.id == mid).first())
    assert kept is not None and kept.deleted_at is not None
    kept_ms = (db_session.query(Membership).execution_options(include_deleted=True)
               .filter(Membership.member_id == mid).first())
    assert kept_ms is not None and kept_ms.deleted_at is not None


def test_family_list_excludes_soft_deleted(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    client.delete(f"/api/v1/families/{member.id}", headers=admin_headers)
    listing = client.get("/api/v1/families", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    ids = [f["id"] for f in listing.json()["items"]]
    assert member.id not in ids


def test_reregister_same_email_after_soft_delete(client, db_session, admin_headers):
    member = _create_family(client, db_session, email="x@example.com")
    assert client.delete(f"/api/v1/families/{member.id}", headers=admin_headers).status_code == 204
    # Opnieuw inschrijven met hetzelfde e-mail/jaar mag: de dedup ziet de
    # soft-deleted niet en de partiële uniciteit blokkeert niet.
    r2 = client.post("/api/v1/families", json=_payload("x@example.com"))
    assert r2.status_code == 201, r2.text


def test_recreate_membership_for_same_member_year_after_soft_delete(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    ms = db_session.query(Membership).filter(Membership.member_id == member.id).first()
    year = ms.year
    assert client.delete(f"/api/v1/memberships/{ms.id}", headers=admin_headers).status_code == 204
    # Nieuw lidmaatschap voor hetzelfde gezin+jaar mag (partiële uniciteit).
    r = client.post(f"/api/v1/families/{member.id}/memberships",
                    json={"year": year}, headers=admin_headers)
    assert r.status_code in (200, 201), r.text


def test_soft_delete_still_recorded_in_member_changes(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    client.delete(f"/api/v1/families/{member.id}", headers=admin_headers)
    changes = client.get("/api/v1/admin/member-changes",
                         params={"since": date.today().isoformat()}, headers=admin_headers).json()
    assert any(c["operation_label"] == "Verwijderd" for c in changes)

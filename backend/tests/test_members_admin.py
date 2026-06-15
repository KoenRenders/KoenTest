"""#160 — dekking van de admin-CRUD/leespaden in members.py (was 39%).

Exerceert de admin-gated lijst/detail-endpoints en de read-builders
(_build_family_response / _person_to_schema), plus admin-lidmaatschap aanmaken.
"""
from tests.conftest import seed_postal_code


def _family_payload(email="admincrud@example.com"):
    return {
        "street": "Teststraat", "house_number": "1", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [
            {"last_name": "Lid", "first_name": "Hoofd", "email": email,
             "mobile": "0470000000", "relation_type": "HOOFDLID"},
        ],
    }


def _make_family(client, db_session):
    seed_postal_code(db_session)
    resp = client.post("/api/v1/families", json=_family_payload())
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_admin_family_endpoints_require_admin(client, db_session):
    assert client.get("/api/v1/families").status_code in (401, 403)
    assert client.get("/api/v1/members").status_code in (401, 403)
    assert client.get("/api/v1/memberships").status_code in (401, 403)


def test_admin_lists_and_detail(client, db_session, admin_headers):
    member_id = _make_family(client, db_session)

    fams = client.get("/api/v1/families", headers=admin_headers)
    assert fams.status_code == 200
    assert fams.json()["total"] >= 1

    fam = client.get(f"/api/v1/families/{member_id}", headers=admin_headers)
    assert fam.status_code == 200
    body = fam.json()
    assert body["id"] == member_id
    assert len(body["members"]) >= 1
    assert body["postal_code"] == "2400"

    members = client.get("/api/v1/members", headers=admin_headers)
    assert members.status_code == 200 and members.json()["total"] >= 1

    assert client.get(f"/api/v1/members/{member_id}", headers=admin_headers).status_code == 200

    mships = client.get("/api/v1/memberships", headers=admin_headers)
    assert mships.status_code == 200 and len(mships.json()) >= 1  # registratie maakte er een

    persons = client.get("/api/v1/persons", headers=admin_headers)
    assert persons.status_code == 200 and len(persons.json()) >= 1


def test_admin_get_family_not_found(client, db_session, admin_headers):
    assert client.get("/api/v1/families/999999", headers=admin_headers).status_code == 404


def test_admin_create_membership_sets_validity(client, db_session, admin_headers):
    """create_membership (admin, per member) zet een geldigheidsperiode (#143)."""
    member_id = _make_family(client, db_session)
    resp = client.post(
        f"/api/v1/members/{member_id}/memberships",
        json={"year": 2099, "is_active": True},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid_from"] == "2099-01-01"
    assert body["valid_to"] == "2099-12-31"

"""#160 — the board's reads and writes on households, as the members screen makes
them: the list, one household (`_build_family_response`, `_person_to_schema`) and
a membership for a year.

Since CR-13 phase 4b (#1251) asked of `membership.household_service`, the
functions the screen `/admin/leden` calls: the JSON routes that passed the same
calls on are gone, none had a caller.
"""

import pytest
from fastapi import HTTPException

from app.domains.mdm.api import list_persons
from app.domains.membership import household_service
from app.domains.membership.schemas_member import MembershipCreate
from tests.conftest import seed_postal_code, seeded_admin, sign_up_at_the_door


def _family_payload(email="admincrud@example.com"):
    return {
        "street": "Teststraat",
        "house_number": "1",
        "postal_code": "2400",
        "payment_method": "transfer",
        "members": [
            {
                "last_name": "Lid",
                "first_name": "Hoofd",
                "email": email,
                "mobile": "0470000000",
                "date_of_birth": "1980-01-01",
                "gender_code": "M",
                "relation_type": "HOOFDLID",
            },
        ],
    }


def _make_family(client, db_session):
    seed_postal_code(db_session)
    resp = sign_up_at_the_door(client, json=_family_payload())
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_the_members_screen_asks_a_session(client, db_session):
    """Without a session the back office answers with the way to the sign-in. The
    three JSON routes each refused a visitor with 401; the screen is what is left."""
    client.cookies.clear()
    answer = client.get("/admin/leden", follow_redirects=False)
    assert answer.status_code == 303 and "/aanmelden" in answer.headers["location"]


def test_admin_lists_and_detail(client, db_session):
    member_id = _make_family(client, db_session)
    admin = seeded_admin(db_session)

    fams = household_service.list_families(db_session, _admin=admin)
    assert fams.total >= 1
    assert member_id in [family.id for family in fams.items]

    fam = household_service.get_family(db_session, member_id, _admin=admin)
    assert fam.id == member_id
    assert len(fam.members) >= 1
    assert fam.postal_code == "2400"

    assert len(list_persons(db_session)) >= 1


def test_admin_get_family_not_found(client, db_session):
    with pytest.raises(HTTPException) as refused:
        household_service.get_family(db_session, 999999)
    assert refused.value.status_code == 404


def test_admin_create_membership_sets_validity(client, db_session):
    """A membership the board adds for a year gets its validity period (#143)."""
    member_id = _make_family(client, db_session)

    made = household_service.create_membership_for_family(
        db_session,
        member_id,
        MembershipCreate(year=2099, is_active=True),
        admin=seeded_admin(db_session),
    )

    assert made.valid_from.isoformat() == "2099-01-01"
    assert made.valid_to.isoformat() == "2099-12-31"

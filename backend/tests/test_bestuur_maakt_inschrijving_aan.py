"""#1192 — the board adds a registration itself.

Koen, 26 September 2026: eight people join a free activity, and he wants to enter
them without using the public form. Until now one place in the whole backend
created a `Registration`: the public route. The board gets a way in of its own —
`/admin/activiteiten/<id>/inschrijvingen/nieuw` — that saves through the SAME
implementation (`router.create_registration`).

The five checks the issue asks for:

1. a board registration exists like any other, and shows on the activity's tab;
2. the required fields hold here too, with the public form's message;
3. **the registration does not hang on the board member who sends the form** —
   the sharpest edge: taken from the session, every board registration would make
   the board member a participant in every report that groups by person;
4. the limit per e-mail address per component does NOT apply to the board
   (recommended in #1192: it is a brake against the public, and the board enters
   its own contact details for people who have none) — a choice, pinned here;
5. there is ONE implementation: the board route goes through
   `create_registration`.

Broken on purpose to check that these tests can go red:
- the board route calling the public `register_for_activity` with the signed-in
  person (as the public way does) → test 3 falls over on `person_id`;
- `contact_refusal` taken out of the board route → test 2 falls over: a missing
  phone number is then refused by the service with another message, a missing
  e-mail address by the schema;
- `board=True` changed to `board=False` in `board_register_for_activity` → test 4
  falls over on the fourth registration;
- the board route creating the `Registration` itself instead of calling the
  facade → test 5 falls over (the spy sees no call).
"""
import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import (SEEDED_ADMIN_EMAIL, create_test_family,
                            seed_activity_with_product)

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def board(client, db_session):
    """The seeded admin, who is ALSO a member: the main member of a household,
    with the admin's e-mail address.

    That is what makes test 3 mean something — the public way resolves the
    session to exactly this person (`login_person_for_email` wants a household),
    so a registration taken from the session would hang on it. A bare person
    without a household is not found, and the test would then prove nothing:
    that is what its first version did.
    """
    _member, person = create_test_family(db_session, email=SEEDED_ADMIN_EMAIL)
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"csrf": csrf_token_for(value), "person_id": person.id}


@pytest.fixture
def activity(db_session):
    activiteit, onderdeel, product = seed_activity_with_product(db_session, price="0",
                                                               is_free=True)
    return activiteit, onderdeel, product


def _add(client, board, activity, **fields):
    activiteit, onderdeel, product = activity
    data = {"onderdeel": str(onderdeel.id), "contact_name": "Bestuur Raak",
            "contact_email": "bestuur-1192@example.org", "phone": "0470000000",
            f"product_{product.id}": "8", "remarks": "Acht namen van de papieren lijst",
            **fields}
    return client.post(f"/admin/activiteiten/{activiteit.id}/inschrijvingen/nieuw",
                       data=data, headers={"X-CSRF-Token": board["csrf"],
                                           "HX-Request": "true"})


def _registrations(db, activity):
    return db.query(Registration).filter(Registration.activity_id == activity[0].id).all()


def test_the_board_adds_a_registration_that_shows_like_any_other(client, db_session,
                                                                 board, activity):
    resp = _add(client, board, activity)

    assert resp.status_code == 200, resp.text[:300]
    [reg] = _registrations(db_session, activity)
    assert resp.headers.get("HX-Redirect") == f"/admin/inschrijvingen/{reg.id}"
    assert sum(i.quantity for i in reg.items) == 8
    tab = client.get(f"/admin/activiteiten/{activity[0].id}/inschrijvingen").text
    assert "Bestuur Raak" in tab


@pytest.mark.parametrize("missing", ["contact_email", "phone"])
def test_the_required_fields_hold_for_the_board_too(client, db_session, board,
                                                    activity, missing):
    resp = _add(client, board, activity, **{missing: ""})

    assert "Vul naam, e-mailadres en mobiel nummer in." in resp.text, resp.text[:400]
    assert _registrations(db_session, activity) == []


def test_the_registration_does_not_hang_on_the_board_member(client, db_session,
                                                            board, activity):
    _add(client, board, activity)

    [reg] = _registrations(db_session, activity)
    assert reg.person_id is None, (
        f"the registration hangs on person {reg.person_id}, the board member who "
        f"sent the form (person {board['person_id']})")


def test_the_limit_per_address_does_not_stop_the_board(client, db_session, board,
                                                       activity):
    for _ in range(4):
        resp = _add(client, board, activity)
        assert resp.headers.get("HX-Redirect"), resp.text[:400]

    assert len(_registrations(db_session, activity)) == 4


def test_the_board_route_uses_the_one_implementation(client, db_session, board,
                                                     activity, monkeypatch):
    from app.domains.activities import router

    calls = []
    real = router.create_registration

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(router, "create_registration", spy)
    _add(client, board, activity)

    assert len(calls) == 1, "the board route did not go through create_registration"
    assert calls[0]["person_id"] is None and calls[0]["board"] is True

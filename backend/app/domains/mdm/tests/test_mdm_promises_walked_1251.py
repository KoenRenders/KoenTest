"""CR-13 phase 4c, C8 (#1251): three promises of mdm's templates, walked by hand.

A `required` in a template is a promise: the browser refuses an empty field, so
the server must too — or a request that does not come from that browser stores
what the screen says cannot be stored. The rules gate walks each promise from the
template to a column that keeps it (`collect_promises`). Three of mdm's it cannot
follow (`PROMISE_UNWALKABLE`):

- `_leden_adres_velden.html`: `street` and `house_number` — the partial has no
  `<form>` of its own; two screens include it, each in its own form;
- `leden_import.html`: `file` — an upload is no column.

So each is walked here, by posting what the browser would refuse to every form
that makes the promise, and asserting the refusal and that nothing was stored.
"""

from __future__ import annotations

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Address, Member, PostalCode
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family, nieuw_lid_velden

pytestmark = pytest.mark.ui_serverrendered

WHOLE = {"street": "Nieuwstraat", "house_number": "7", "bus_number": "", "postal_code": "2399"}
#: mdm's one rule for an address (`require_whole_address`, #1603), which the
#: portal's save always gave — the reason every form below must refuse for.
RULE = "Een adres heeft een straat, een huisnummer en een postcode nodig."


def _login(client) -> dict[str, str]:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


@pytest.fixture
def postal_code(db_session):
    db_session.add(PostalCode(postal_code="2399", municipality="Proefdorp"))
    db_session.commit()


# ── `street` and `house_number`, on the address card of a household ──────────


@pytest.mark.parametrize("empty", ["street", "house_number"])
def test_a_first_address_without_it_is_refused(client, db_session, postal_code, empty):
    household, _main = create_test_family(db_session, email="belofte-a@example.com")
    db_session.commit()

    response = client.post(
        f"/admin/leden/gezin/{household.id}/adres",
        data={**WHOLE, empty: ""},
        headers=_login(client),
    )

    assert response.status_code == 422, f"{empty} empty was accepted: {response.status_code}"
    assert RULE in response.text, response.text[:300]
    assert db_session.query(Address).count() == 0, "an address without it was stored"


@pytest.mark.parametrize("empty", ["street", "house_number"])
def test_an_address_that_is_there_cannot_lose_it(client, db_session, postal_code, empty):
    household, main = create_test_family(db_session, email="belofte-b@example.com")
    db_session.commit()
    headers = _login(client)
    stored = client.post(f"/admin/leden/gezin/{household.id}/adres", data=WHOLE, headers=headers)
    assert stored.status_code == 200, "the set-up stored no address — the test looks at nothing"

    response = client.post(
        f"/admin/leden/gezin/{household.id}/adres", data={**WHOLE, empty: ""}, headers=headers
    )

    db_session.expire_all()
    address = db_session.query(Address).filter(Address.person_id == main.id).one()
    assert getattr(address, empty) == WHOLE[empty], (
        f"the address lost its {empty} (the answer was {response.status_code})"
    )
    assert response.status_code == 422, f"{empty} emptied was accepted: {response.status_code}"
    assert RULE in response.text, response.text[:300]


# ── `street` and `house_number`, on the form of a new household ──────────────


@pytest.mark.parametrize("empty", ["street", "house_number"])
def test_a_new_household_without_it_is_refused(client, db_session, empty):
    fields = nieuw_lid_velden(db_session, **{empty: ""})
    households = db_session.query(Member).count()

    response = client.post("/admin/leden", data=fields, headers=_login(client))

    assert response.status_code == 422, f"{empty} empty was accepted: {response.status_code}"
    assert RULE in response.text, response.text[:300]
    assert db_session.query(Member).count() == households, "a household was stored without it"


def test_the_new_household_form_does_store_a_whole_one(client, db_session):
    """The way that is not refused: without it, a form that refuses everything
    would pass the two tests above."""
    fields = nieuw_lid_velden(db_session)
    households = db_session.query(Member).count()

    response = client.post("/admin/leden", data=fields, headers=_login(client))

    assert response.status_code == 204, response.text[:300]
    assert db_session.query(Member).count() == households + 1


# ── `file`, on the member import ─────────────────────────────────────────────


def test_the_import_without_a_file_is_refused(client, db_session):
    response = client.post("/admin/leden-import/preview", headers=_login(client))
    assert response.status_code == 422, response.status_code


def test_the_import_with_an_empty_file_is_refused(client, db_session):
    response = client.post(
        "/admin/leden-import/preview",
        files={"file": ("ledenrapport.xls", b"", "application/vnd.ms-excel")},
        headers=_login(client),
    )
    assert "Leeg bestand." in response.text, response.text[:300]

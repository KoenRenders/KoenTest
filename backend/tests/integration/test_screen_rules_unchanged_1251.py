"""CR-13 phase 4c, cut C4-2 (#1251): three rules leave a screen module — the answers stay.

Three refusals were decided in a screen module and are the rule's own now, each
in the function the screen calls next:

- the address of a household without persons (`mdm/ui.py::adres_opslaan`) →
  `membership.api.update_family_address`;
- a new household without a single filled-in person (`mdm/ui.py::gezin_aanmaken`)
  → `membership.api.family_from_rows`;
- the board's registration form without a component
  (`activities/admin_ui.py::inschrijving_nieuw_opslaan`) →
  `activities.api.board_channel`.

No behaviour changes, so the proof is not a green test but **the same answer and
the same rows on the same input**: every answer below was recorded on the code
BEFORE the move (`master` `76bff045` with the last route cut, `d0a6f15f`) and the
moved code must give it again, character for character (`tests/_snapshot.py`).
Beside each refusal stands the way that is not refused — the address that IS
stored — so a function that refuses everything cannot pass.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from app.domains.activities.api import (
    Activity,
    ActivityProduct,
    ActivitySubRegistration,
    Registration,
)
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Address, ContactDetail, Member, Person, PostalCode
from tests._snapshot import compare, fixed_ids, main_region, normalise
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    create_test_family,
    create_test_member,
    seed_activity_with_product,
)

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "screen_rules_1251"
BEFORE = "the rules left the screen modules (CR-13 phase 4c, C4-2)"
ADDRESS = {"street": "Nieuwstraat", "house_number": "7", "bus_number": "", "postal_code": "2399"}


def _login(client) -> dict[str, str]:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


@pytest.fixture(autouse=True)
def _ids_from_a_fixed_start(db_session):
    """Fixed ids for every row a test makes (`tests/_snapshot.fixed_ids`)."""
    models = (Member, Person, ContactDetail, Address, PostalCode, Activity)
    models += (ActivitySubRegistration, ActivityProduct)
    with fixed_ids(db_session, models):
        yield


def _answer(response, names: dict[int, str]) -> str:
    """The status and what the screen says: the page's own content, or the whole
    answer where it is a fragment or a refusal. Today and this year are masked:
    the screens prefill them."""
    body = main_region(response.text) if "<main" in response.text else response.text
    today = date.today()
    moving = {today.isoformat(): "<TODAY>", str(today.year): "<YEAR>"}
    # A field's example address is copy, not data — and no address outside the
    # reserved domains may stand in a test file of this public repository.
    body = re.sub(r'(placeholder=")[^"]*@[^"]*', r"\1<EXAMPLE-ADDRESS>", body)
    return normalise(f"{response.status_code}\n{body}", names, moving)


def _postal_code(db) -> None:
    db.add(PostalCode(postal_code="2399", municipality="Proefdorp"))
    db.flush()


def test_an_address_for_a_household_without_persons_is_refused_as_before(client, db_session):
    household = create_test_member(db_session)
    _postal_code(db_session)
    db_session.commit()

    response = client.post(
        f"/admin/leden/gezin/{household.id}/adres", data=ADDRESS, headers=_login(client)
    )

    # Recorded again with #1831: the address card says it in its message line —
    # the kit's refusal, a 422 — where it was a bare 400 the screen could not
    # show; and the card of the stored address below carries that line.
    assert response.status_code == 422
    assert "Gezin zonder personen." in response.text
    compare(SNAPSHOTS, "address_refused", _answer(response, {household.id: "<HOUSEHOLD>"}), BEFORE)
    assert db_session.query(Address).count() == 0


def test_an_address_for_a_household_is_stored_as_before(client, db_session):
    household, main = create_test_family(db_session, email="adres-1251@example.com")
    _postal_code(db_session)
    db_session.commit()

    response = client.post(
        f"/admin/leden/gezin/{household.id}/adres", data=ADDRESS, headers=_login(client)
    )

    assert response.status_code == 200, response.text[:300]
    names = {household.id: "<HOUSEHOLD>", main.id: "<MAIN>"}
    compare(SNAPSHOTS, "address_stored", _answer(response, names), BEFORE)
    db_session.expire_all()
    stored = db_session.query(Address).one()
    assert (stored.person_id, stored.street, stored.house_number, stored.bus_number) == (
        main.id,
        "Nieuwstraat",
        "7",
        None,
    )
    assert stored.postal_code.postal_code == "2399"


@pytest.mark.parametrize(
    "name, fields",
    [
        ("create_refused_empty", {}),
        # Only an address: still nobody to be the main member.
        ("create_refused_address_only", ADDRESS),
        # A row without a name is an empty row, and does not count.
        ("create_refused_nameless_row", {**ADDRESS, "m0_email": "leeg-1251@example.com"}),
    ],
)
def test_a_new_household_without_a_person_is_refused_as_before(client, db_session, name, fields):
    _postal_code(db_session)
    db_session.commit()
    households = db_session.query(Member).count()

    response = client.post("/admin/leden", data=fields, headers=_login(client))

    assert response.status_code == 422
    assert "Vul minstens het hoofdlid in." in response.text
    compare(SNAPSHOTS, name, _answer(response, {}), BEFORE)
    assert db_session.query(Member).count() == households


def test_the_boards_form_without_a_component_is_refused_as_before(client, db_session):
    activity, component, _product = seed_activity_with_product(db_session)
    db_session.commit()

    response = client.post(
        f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw",
        data={"contact_name": "Proef Persoon", "contact_email": "proef-1251@example.com"},
        headers=_login(client),
    )

    assert response.status_code == 200
    assert "Kies een onderdeel." in response.text
    names = {activity.id: "<ACTIVITY>", component.id: "<COMPONENT>"}
    compare(SNAPSHOTS, "board_form_refused", _answer(response, names), BEFORE)
    assert db_session.query(Registration).count() == 0


@pytest.mark.parametrize(
    "name, path, fields",
    [
        ("circle_add_refused", "/admin/vergaderingen/kring", {"person_id": "PERSON"}),
        (
            "circle_new_person_refused",
            "/admin/vergaderingen/kring/nieuw",
            {"first_name": "Proef", "last_name": "Kring", "person_email": "kring-1251@example.com"},
        ),
    ],
)
def test_the_circle_without_an_organisation_is_refused_as_before(
    client, db_session, monkeypatch, name, path, fields
):
    """The test world has its organisation, so the read is made to find none —
    under both names it is reached by: the facade's, which the screen imported
    before the move, and the service's own, which the moved rule calls."""
    import app.domains.mdm.api as mdm_api
    import app.domains.mdm.tenant_service as tenant_service
    from app.domains.mdm.api import Person

    monkeypatch.setattr(mdm_api, "platform_org", lambda db: None)
    monkeypatch.setattr(tenant_service, "platform_org", lambda db: None)
    _household, main = create_test_family(db_session, email="kringlid-1251@example.com")
    db_session.commit()
    persons = db_session.query(Person).count()
    sent = {k: (str(main.id) if v == "PERSON" else v) for k, v in fields.items()}

    response = client.post(path, data=sent, headers=_login(client))

    assert response.status_code == 200
    assert "Er is nog geen organisatie ingesteld." in response.text
    compare(SNAPSHOTS, name, _answer(response, {main.id: "<MAIN>"}), BEFORE)
    assert db_session.query(Person).count() == persons

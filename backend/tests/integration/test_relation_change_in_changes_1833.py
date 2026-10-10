"""A changed relation in a household appears under Wijzigingen (#1833).

The board retypes the list of changes into the national programme. Changing a
person's relation on the Leden screen (partner ↔ kind) wrote no history row, so
it was the one change of a household that never reached that list — found in
the recording of the board's writes (#1251, C6-2).

It writes its row now, through mdm's own history, with the board member who did
it; the list and its export say what the relation was and what it is.

Walked through the screens: the person's card is saved on the Leden screen, and
the list is read where the board reads it — the page and the export file.

Proven red on the code before: the first three tests fail (no row, so nothing
in the list or the file); the fourth passes before and after — a save that
changes no relation writes no row.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import MemberPerson, MemberPersonHistory, PostalCode
from app.domains.reporting.api import member_changes_since
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

SAID = "relatie PARTNER → KIND"


def _person(n: int, first_name: str, **more) -> dict:
    fields = {
        "first_name": first_name,
        "last_name": "Proef",
        "date_of_birth": "1980-03-04",
        "gender_code": "F",
        "email": "",
        "phone": "",
        "mobile": "",
    }
    return {f"m{n}_{name}": value for name, value in (fields | more).items()}


NEW = {"street": "Proefstraat", "house_number": "12", "bus_number": "", "postal_code": "2399"}
NEW |= _person(0, "Hanne", email="hanne-1833@example.com", mobile="0470 00 00 01")
NEW |= _person(1, "Bram", gender_code="M")


@pytest.fixture
def headers(client, db_session):
    db_session.add(PostalCode(postal_code="2399", municipality="Proefdorp"))
    db_session.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


@pytest.fixture
def partner(client, db_session, headers) -> tuple[int, MemberPerson]:
    """A household of a main member and a partner, made through the screen: its
    id and the partner's link."""
    made = client.post("/admin/leden", data=NEW, headers=headers)
    assert made.status_code == 204, made.text
    household = int(made.headers["HX-Redirect"].rsplit("/", 1)[-1])
    link = (
        db_session.query(MemberPerson)
        .filter(MemberPerson.member_id == household, MemberPerson.relation_type == "PARTNER")
        .one()
    )
    return household, link


def _save_card(client, headers, household: int, link: MemberPerson, relation: str):
    card = {name[3:]: value for name, value in _person(9, "Bram", gender_code="M").items()}
    answer = client.post(
        f"/admin/leden/gezin/{household}/persoon/{link.person_id}",
        data=card | {"relation_type": relation},
        headers=headers,
    )
    assert answer.status_code == 200, answer.text


def _link_rows(db, link: MemberPerson) -> list[MemberPersonHistory]:
    db.expire_all()
    return (
        db.query(MemberPersonHistory)
        .filter(MemberPersonHistory.member_person_id == link.id)
        .order_by(MemberPersonHistory.id)
        .all()
    )


def test_a_changed_relation_writes_its_history_row(client, db_session, headers, partner):
    household, link = partner

    _save_card(client, headers, household, link, "KIND")

    rows = _link_rows(db_session, link)
    assert [(row.operation, row.relation_type) for row in rows] == [
        ("insert", "PARTNER"),
        ("update", "KIND"),
    ]
    change = rows[-1]
    assert (change.action, change.source, change.actor) == (
        "relation_changed",
        "admin_update",
        SEEDED_ADMIN_EMAIL,
    )


def test_the_list_of_changes_says_what_it_was_and_what_it_is(client, db_session, headers, partner):
    household, link = partner
    _save_card(client, headers, household, link, "KIND")

    feed = member_changes_since(db_session, date(2000, 1, 1))
    said = [row for row in feed if row["entity"] == "Gezinslid" and row["summary"] == SAID]
    assert len(said) == 1, [row["summary"] for row in feed if row["entity"] == "Gezinslid"]
    assert said[0]["actor"] == SEEDED_ADMIN_EMAIL

    page = client.get("/admin/ledenwijzigingen")
    assert page.status_code == 200
    assert SAID in page.text, "the page of changes does not show the changed relation"


def test_the_export_holds_the_same_row(client, db_session, headers, partner):
    household, link = partner
    _save_card(client, headers, household, link, "KIND")

    answer = client.get("/admin/ledenwijzigingen/export?since=2000-01-01")

    assert answer.status_code == 200
    sheet = zipfile.ZipFile(io.BytesIO(answer.content)).read("content.xml").decode("utf-8")
    assert SAID in sheet, "the export does not hold the changed relation"


def test_a_save_that_changes_no_relation_writes_no_row(client, db_session, headers, partner):
    """The card sends its relation at every save; the same relation is no change."""
    household, link = partner

    _save_card(client, headers, household, link, "PARTNER")

    assert [row.operation for row in _link_rows(db_session, link)] == ["insert"]

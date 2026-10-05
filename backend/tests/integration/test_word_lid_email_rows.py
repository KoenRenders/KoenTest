"""#1246 — the public Word lid form takes several e-mail addresses per person.

Since v2.6.0 a person's addresses are rows (#1174, #1219), on the admin side and in
the family portal; since #1246 on the public form too, so a family need not wait
for its first login to add a second address.

Since #1590 the rows are the kit's repeating group, the same as on "Mijn gezin":
every address is a row `e_order.<person>=<key>` with its `e.<key>.value`, and
**the marked row is the main address** — one hidden `e_primary.<person>` carries
the key of the row with the "hoofdadres" tag. Until #1590 the first row was the
main one by its position; a visitor can now mark another.

These tests post the form the way the browser does. That the rows reach the
database in a committed transaction, read through a second connection, is the
e2e test's job: inside this suite the request shares the test's session, which
cannot tell a flush from a commit.

Each storing test is one of a pair that differs in one thing — one address or
two, the first row marked or the second — so the difference in what is stored
is what the form's rows caused.
"""

from __future__ import annotations

import re

import pytest

from app.domains.mdm.api import ContactDetail, Person
from tests.conftest import signup_fields

pytestmark = pytest.mark.ui_serverrendered


def _form(db, *addresses: str, **changes) -> dict:
    return signup_fields(
        db,
        emails=addresses,
        **{"h.n0.first_name": "Rij", "h.n0.last_name": "Proef-1246"},
        **changes,
    )


def _addresses(db, email: str) -> dict[str, bool]:
    """The e-mail rows of the person who owns `email`, as {value: is_primary}."""
    db.expire_all()
    person_id = db.query(ContactDetail.person_id).filter(ContactDetail.value == email).scalar()
    assert person_id, f"no person was stored with {email}"
    person = db.get(Person, person_id)
    return {
        c.value: bool(c.is_primary)
        for c in person.contact_details
        if c.contact_type_code == "EMAIL"
    }


def _rows(html: str, group: str) -> list[str]:
    """The rows of one repeating group on the page, without its template."""
    start = html.index(f'data-repeating-group="{group}"')
    block = html[start : html.index("<template data-group-template>", start)]
    return re.split(r"(?=<div data-group-row )", block)[1:]


def test_the_form_draws_one_row_marked_as_the_main_address(client):
    html = client.get("/lid-worden").text
    rows = _rows(html, "e_order.n0")
    assert len(rows) == 1, f"the main member starts with one e-mail row, found {len(rows)}"
    (row,) = rows
    assert 'name="e_order.n0" value="n0e"' in row and 'name="e.n0e.value"' in row
    assert 'name="e_primary.n0" value="n0e"' in html, "the group does not carry which row is main"
    tag = re.search(r"<span data-row-one-tag[^>]*>", row)
    assert tag and "hidden" not in tag.group(0), "the first row carries no visible hoofdadres tag"
    assert "hoofdadres" in row
    remove = re.search(r'<button[^>]*data-row-action="remove"[^>]*>', row)
    assert remove and "hidden" in remove.group(0), "the main row must not be removable"


def test_a_row_added_in_the_page_is_a_removable_extra_address(client):
    """What "+ E-mailadres" adds is the group's template: not the main address,
    with "Maak hoofdadres" and "Verwijderen" in its menu."""
    html = client.get("/lid-worden").text
    start = html.index(
        "<template data-group-template>", html.index('data-repeating-group="e_order.n0"')
    )
    template = html[start : html.index("</template>", start)]
    assert 'name="e_order.n0" value="__E__"' in template and 'name="e.__E__.value"' in template
    tag = re.search(r"<span data-row-one-tag[^>]*>", template)
    assert tag and "hidden" in tag.group(0), "an added row is never the main address by itself"
    for action in ("choose", "remove"):
        button = re.search(rf'<button[^>]*data-row-action="{action}"[^>]*>', template)
        assert button and "hidden" not in button.group(0), f"an added row offers no '{action}'"


def test_the_boards_extra_row_is_still_served(client):
    """`/lid-worden/email-rij` stays for the board's "new member" screen, which
    still builds its persons from the old rows (#1246)."""
    html = client.get("/lid-worden/email-rij?member=0&index=1727000000001&nummer=2").text
    assert 'name="m0_email_new_1727000000001"' in html
    assert "hoofdadres" not in html, "an added row is never the primary address"
    assert "Verwijderen" in html


def test_two_addresses_are_stored_with_the_marked_one_as_primary(client, db_session):
    first, second = "rij.een-1246@example.com", "rij.twee-1246@example.com"
    response = client.post("/lid-worden", data=_form(db_session, first, second))
    assert response.status_code == 200, response.text[:500]
    assert _addresses(db_session, first) == {first: True, second: False}


def test_the_mark_decides_not_the_order_of_the_rows(client, db_session):
    """New with #1590: the second row is marked, so the second is the main one."""
    first, second = "rij.eerst-1246@example.com", "rij.gekozen-1246@example.com"
    response = client.post(
        "/lid-worden", data=_form(db_session, first, second, **{"e_primary.n0": "n0e1"})
    )
    assert response.status_code == 200, response.text[:500]
    assert _addresses(db_session, first) == {first: False, second: True}


def test_one_address_is_the_primary_one(client, db_session):
    only = "rij.alleen-1246@example.com"
    client.post("/lid-worden", data=_form(db_session, only))
    assert _addresses(db_session, only) == {only: True}


def test_the_same_address_twice_is_stored_once(client, db_session):
    address = "rij.dubbel-1246@example.com"
    client.post("/lid-worden", data=_form(db_session, address, address.upper()))
    assert _addresses(db_session, address) == {address: True}


def test_an_empty_extra_row_adds_nothing(client, db_session):
    address = "rij.leeg-1246@example.com"
    client.post("/lid-worden", data=_form(db_session, address, ""))
    assert _addresses(db_session, address) == {address: True}


def test_the_second_address_logs_in(client, db_session):
    """The reason this issue exists: every address logs in (#1174)."""
    from app.domains.auth.api import login_person_for_email

    first, second = "rij.login1-1246@example.com", "rij.login2-1246@example.com"
    client.post("/lid-worden", data=_form(db_session, first, second))
    db_session.expire_all()
    owner = db_session.query(ContactDetail.person_id).filter(ContactDetail.value == first).scalar()
    person = login_person_for_email(db_session, second)
    assert person is not None, "the second address does not log in"
    assert getattr(person, "id", person) == owner


def test_a_refusal_leaves_the_rows_on_the_page_alone(client, db_session):
    """Until #1590 a refused form came back as a whole page, and this test read
    the typed addresses back out of it. Now the refusal answers the banner alone
    for the page's message line, so the rows are never redrawn: what was typed
    stays because nothing replaces it. Here: the answer is that banner and
    nothing of the page, it names the refused row, and nothing was stored."""
    first, second = "rij.terug1-1246@example.com", "rij.terug2@"
    response = client.post("/lid-worden", data=_form(db_session, first, second))
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == "#lid-worden-melding"
    assert response.headers["HX-Reselect"] == "[data-save-refusal]"
    assert "<html" not in response.text.lower() and "data-form-flow" not in response.text
    assert re.findall(r'data-error-for="([^"]+)"', response.text) == ["e.n0e1.value"]
    assert db_session.query(ContactDetail).filter(ContactDetail.value == first).count() == 0

"""#1458 — an admin link brings you to that page after signing in.

Koen, 2 October 2026: he sends a board member a link to a back-office screen.
Signed out, that link answered 401 with the bare JSON `{"detail":"Niet
aangemeld"}` — the guard set `Location`, but a browser does not follow it on a
401. Now a plain GET redirects (303) to `/aanmelden?terug=<the page>`, and the
code step and the mail link both bring the person back there, through the
`terug` and `veilige_terug` of #1437. htmx requests and other methods keep
the 401; signed in without the role stays 403.

Proven red against master (`e73da3ff`): the signed-out GET answered 401, so the
first test failed on the status and the walk-throughs never got a `terug`.
"""

import re
from html import unescape
from urllib.parse import parse_qs, urlparse

import pytest

from app.domains.auth.api import User, UserRole
from tests._queued_mail import queued_link
from tests.conftest import sent_to_sign_in

pytestmark = pytest.mark.ui_serverrendered

EMAIL = "bestuurslid-1458@example.com"
PAGE = "/admin/leden?q=Peeters&status=actief"


@pytest.fixture
def board_member(db_session):
    user = User(email=EMAIL, is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db_session.commit()
    return EMAIL


@pytest.fixture
def mail_link(monkeypatch, db_session):
    """The link the sign-in mail carries, read from the queue it waits in, and a
    known code beside it."""
    from app.domains.auth import login as auth_login

    monkeypatch.setattr(auth_login, "_generate_otp", lambda: "585858")
    return lambda: queued_link(db_session, EMAIL)


def _way_back_on_the_sign_in_page(client) -> str:
    """Follow the admin link as a browser does, and read the `terug` the sign-in
    page carries in its form — what the next step will post."""
    redirect = client.get(PAGE, follow_redirects=False)
    page = client.get(redirect.headers["location"])
    found = re.search(r'name="terug" value="([^"]*)"', page.text)
    assert found, "the sign-in page carries no way back"
    return unescape(found.group(1))


def test_a_signed_out_admin_link_redirects_with_its_path_and_query(client):
    assert sent_to_sign_in(client, PAGE)
    assert sent_to_sign_in(client, "/admin/activiteiten/13/inschrijvingen")


def test_htmx_and_other_methods_keep_their_answer(client):
    """An htmx request cannot use a 303 to a full page; it keeps `HX-Redirect`.
    A POST is no link someone was sent: without a session the CSRF guard
    refuses it first, as before."""
    htmx = client.get("/admin/leden", headers={"HX-Request": "true"}, follow_redirects=False)
    assert htmx.status_code == 401 and htmx.headers.get("HX-Redirect") == "/aanmelden"
    post = client.post("/admin/rapporten", follow_redirects=False)
    assert post.status_code == 403 and "location" not in post.headers


def test_signed_in_without_the_role_is_still_refused(client, db_session):
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    db_session.add(User(email="geen-rol-1458@example.com", is_active=True))
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value("geen-rol-1458@example.com"))
    answer = client.get("/admin/leden", follow_redirects=False)
    assert answer.status_code == 403 and "Geen toegang" in answer.text


def test_the_code_brings_you_to_the_admin_page(client, board_member, mail_link):
    way_back = _way_back_on_the_sign_in_page(client)
    assert way_back == PAGE

    client.post("/aanmelden", data={"email": EMAIL, "terug": way_back})
    done = client.post(
        "/aanmelden/code", data={"email": EMAIL, "code": "585858", "terug": way_back}
    )
    assert done.headers.get("HX-Redirect") == PAGE, "the workbench, not the page asked for"
    assert client.get(PAGE).status_code == 200


def test_the_mail_link_brings_you_to_the_admin_page(client, board_member, mail_link):
    way_back = _way_back_on_the_sign_in_page(client)
    client.post("/aanmelden", data={"email": EMAIL, "terug": way_back})

    link = urlparse(mail_link())
    assert parse_qs(link.query)["terug"] == [PAGE]
    landed = client.get(f"{link.path}?{link.query}", follow_redirects=False)
    assert landed.status_code == 302 and landed.headers["location"] == PAGE
    assert client.get(PAGE).status_code == 200


@pytest.mark.parametrize("foreign", ["https://evil.example/admin", "//evil.example/admin"])
def test_a_foreign_way_back_in_the_code_step_is_refused(client, board_member, mail_link, foreign):
    client.post("/aanmelden", data={"email": EMAIL, "terug": foreign})
    done = client.post("/aanmelden/code", data={"email": EMAIL, "code": "585858", "terug": foreign})
    # A foreign way back is dropped; the fallback is the site's landing (#1740).
    assert done.headers.get("HX-Redirect") == "/"

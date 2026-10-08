"""#1437 — signing in remembers the page asked for, also through the mail link.

The case Koen had in mind: a renewal mail to every member, linking to the
household portal. A board member who is also a member clicked it and, after
signing in, landed on the workbench — the landing by role — instead of in the
portal. Now `/leden/gezin` sends a signed-out visitor to `/aanmelden?terug=…`,
the code step and the mail link both follow `terug`, and both check it with the
one `veilige_terug`: only a path on this site counts.

Proven red against master (`cbd15865`): the portal's redirect carried no
`terug`, and `/login/verify` ignored it.
"""

from urllib.parse import parse_qs, urlparse

import pytest

from app.domains.auth.api import User, UserRole
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

EMAIL = "bestuur-en-lid-1437@example.com"


@pytest.fixture
def board_member_who_is_a_member(db_session):
    """An ADMIN — whose landing is the workbench — with a household of their own."""
    create_test_family(db_session, email=EMAIL)
    user = User(email=EMAIL, is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db_session.commit()
    return EMAIL


@pytest.fixture
def mail_link(monkeypatch):
    """The link the sign-in mail would carry, and the code beside it."""
    from app.domains.auth import login as auth_login

    sent = {}

    def fake_send(*, to_email, magic_link, otp_code):
        sent.update(to=to_email, link=magic_link, code=otp_code)

    monkeypatch.setattr(auth_login, "send_magic_link", fake_send)
    monkeypatch.setattr(auth_login, "_generate_otp", lambda: "424242")
    return sent


def test_the_portal_sends_a_signed_out_visitor_to_sign_in_with_the_way_back(client):
    response = client.get("/leden/gezin", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/aanmelden?terug=/leden/gezin"


def test_the_code_brings_a_board_member_back_to_the_portal(
    client, board_member_who_is_a_member, mail_link
):
    client.get("/aanmelden", params={"terug": "/leden/gezin"})
    client.post("/aanmelden", data={"email": EMAIL, "terug": "/leden/gezin"})
    done = client.post(
        "/aanmelden/code", data={"email": EMAIL, "code": "424242", "terug": "/leden/gezin"}
    )
    assert done.headers.get("HX-Redirect") == "/leden/gezin", "the workbench, not the portal"


def test_the_mail_link_brings_a_board_member_back_to_the_portal(
    client, board_member_who_is_a_member, mail_link
):
    """The sign-in started from the portal; the link in the mail carries the
    page, and following it lands in the portal — not on the workbench."""
    client.post("/aanmelden", data={"email": EMAIL, "terug": "/leden/gezin"})
    link = urlparse(mail_link["link"])
    assert parse_qs(link.query)["terug"] == ["/leden/gezin"]

    landed = client.get(f"{link.path}?{link.query}", follow_redirects=False)
    assert landed.status_code == 302
    assert landed.headers["location"] == "/leden/gezin"


def test_without_a_page_the_mail_link_lands_on_the_account_page(
    client, board_member_who_is_a_member, mail_link
):
    client.post("/aanmelden", data={"email": EMAIL})
    link = urlparse(mail_link["link"])
    assert "terug" not in parse_qs(link.query)
    landed = client.get(f"{link.path}?{link.query}", follow_redirects=False)
    # #1740: a board member who is a member too lands on his account page.
    assert landed.headers["location"] == "/mijn"


@pytest.mark.parametrize("foreign", ["https://evil.example/x", "//evil.example/x"])
def test_a_foreign_way_back_in_the_mail_link_is_ignored(
    client, board_member_who_is_a_member, mail_link, foreign
):
    """A link can be edited: `terug` is checked where it is used, by the one
    `veilige_terug`, and anything that is not a path on this site falls back to
    the landing by role."""
    client.post("/aanmelden", data={"email": EMAIL})
    link = urlparse(mail_link["link"])
    landed = client.get(
        link.path,
        params={**{k: v[0] for k, v in parse_qs(link.query).items()}, "terug": foreign},
        follow_redirects=False,
    )
    assert landed.status_code == 302
    # #1740: a board member who is a member too lands on his account page.
    assert landed.headers["location"] == "/mijn"

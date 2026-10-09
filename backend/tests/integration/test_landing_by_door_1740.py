"""The door decides where someone lands after signing in, not the role (#1740;
Koen, 8 October 2026: "waar men aanlogt komt men terecht").

- signed in on the public site, with no page that asked: the account page
  (`/mijn`) for whoever signs in as a person, the site (`/`) for a session
  without one — **for ADMIN and for FINANCE alone as for a member**;
- **a page that asked comes first**: an `/admin…` page gets its board member
  back (that is how the back office is the door), the renewal opens for a
  member and for a board member;
- which page a role enters the back office by is the back office's own answer
  (`back_office_home`): the public menu's "Admin" leads there — also for
  FINANCE alone, who lands on the site now and had no way in from it;
- two points from the measurement of a double address: one mail text for every
  address that says nobody, and on Personen the badge "dubbel e-mailadres" —
  on both holders, on neither of two members of one household who share one.

Red (each restored after): the role branches put back in `landing_for` → an
ADMIN lands on the workbench and FINANCE on payments; `back_office_home`
answering None for FINANCE → no "Admin" in his menu; the notice's old text →
"meerdere gezinnen"; `address_says_nobody` always False → no badge, and
"Account" on a person whose address signs nobody in.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.domains.auth import login as auth_login
from app.domains.auth.api import (
    SESSION_COOKIE,
    User,
    UserRole,
    back_office_home,
    csrf_token_for,
    landing_for,
    make_session_value,
)
from app.domains.mdm.api import ContactDetail, Member, MemberPerson
from app.kernel.jobs import run_due_jobs
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family, create_test_person

pytestmark = pytest.mark.ui_serverrendered

CODE = "424242"
RENEWAL = "/leden/gezin/vernieuwen"


@pytest.fixture(autouse=True)
def a_known_code(monkeypatch):
    from app.limiter import login_limiter

    monkeypatch.setattr(auth_login, "_generate_otp", lambda: CODE)
    login_limiter._calls.clear()
    yield
    login_limiter._calls.clear()


@pytest.fixture
def sent(monkeypatch):
    from app.domains.mail import service

    captured: list[dict] = []
    monkeypatch.setattr(
        service,
        "_send",
        lambda to_email, subject, body_html, cc=None, email_type="other": captured.append(
            {"to": to_email, "subject": subject, "body": body_html, "type": email_type}
        ),
    )
    return captured


def _board(db, email: str, *roles: str) -> None:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role_code=role))
    db.commit()


def _sign_in(client, email: str, back: str = "") -> str:
    data = {"email": email} | ({"terug": back} if back else {})
    client.post("/aanmelden", data=data)
    done = client.post("/aanmelden/code", data={**data, "code": CODE})
    assert SESSION_COOKIE in done.cookies, done.text[:200]
    return done.headers["HX-Redirect"]


# ── the landing ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("roles", [("ADMIN",), ("FINANCE",), ("OPERATOR",), ()])
def test_on_the_site_everyone_lands_on_the_account_page(client, db_session, sent, roles):
    """A board member who is a member too: the role changes nothing."""
    email = f"lid-{'-'.join(roles) or 'zonder-rol'}-1740@example.org".lower()
    create_test_family(db_session, email=email)
    if roles:
        _board(db_session, email, *roles)
    db_session.commit()
    assert landing_for(db_session, email) == "/mijn"
    assert _sign_in(client, email) == "/mijn"


@pytest.mark.parametrize("roles", [("ADMIN",), ("FINANCE",)])
def test_a_board_user_without_a_person_lands_on_the_site(client, db_session, sent, roles):
    email = f"bestuur-{roles[0].lower()}-1740@example.org"
    _board(db_session, email, *roles)
    assert _sign_in(client, email) == "/"
    assert client.get("/mijn").status_code == 404, "the account page exists without a person"


@pytest.mark.parametrize(
    ("roles", "page"), [(("ADMIN",), "/admin/leden"), (("FINANCE",), "/admin/betalingen")]
)
def test_an_admin_page_that_asked_gets_its_board_member_back(client, db_session, sent, roles, page):
    """The back office as the door: the screen sends its visitor to sign in
    with itself as the page to return to, and the sign-in follows it."""
    email = f"deur-{roles[0].lower()}-1740@example.org"
    create_test_family(db_session, email=email)
    _board(db_session, email, *roles)
    asked = client.get(page, headers={"accept": "text/html"}, follow_redirects=False)
    assert asked.status_code == 303 and asked.headers["location"] == f"/aanmelden?terug={page}"
    assert _sign_in(client, email, back=page) == page
    assert client.get(page).status_code == 200


@pytest.mark.parametrize("roles", [(), ("ADMIN",)])
def test_the_renewal_link_still_opens_the_renewal(client, db_session, sent, roles):
    email = f"vernieuwer-{'bestuur' if roles else 'lid'}-1740@example.org"
    create_test_family(db_session, email=email)
    if roles:
        _board(db_session, email, *roles)
    db_session.commit()
    assert _sign_in(client, email, back=RENEWAL) == RENEWAL


# ── the way into the back office ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("roles", "home"),
    [
        (("ADMIN",), "/admin/werkbank"),
        (("OPERATOR",), "/admin/werkbank"),
        (("FINANCE",), "/admin/werkbank"),
        (("MASTERDATA",), "/admin/werkbank"),
        (("ACCOUNT_ADMIN",), None),
        ((), None),
    ],
)
def test_the_back_office_says_which_page_a_user_enters_by(db_session, roles, home):
    """CR-24 Q13 (Koen, 9 October 2026): one address for everyone with a
    back-office role, the workbench; the branch that sent FINANCE alone to
    payments is gone. A role that bundles nothing has no way in."""
    email = f"home-{'-'.join(roles) or 'none'}-1722@example.org".lower()
    _board(db_session, email, *roles)
    assert back_office_home(db_session, email) == home


@pytest.mark.parametrize(
    ("roles", "href"),
    [(("ADMIN",), "/admin/werkbank"), (("FINANCE",), "/admin/werkbank"), ((), None)],
)
def test_the_public_menu_leads_into_the_back_office_for_whoever_has_a_way_in(
    client, db_session, roles, href
):
    email = f"menu-{'-'.join(roles) or 'lid'}-1740@example.org".lower()
    create_test_family(db_session, email=email)
    if roles:
        _board(db_session, email, *roles)
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(email))
    html = client.get("/mijn").text
    links = re.findall(r'<a href="([^"]+)"[^>]*data-account-item="admin"', html)
    if href is None:
        assert links == [], "a member gets a way into the back office"
    else:
        assert links and set(links) == {href}, links
        assert client.get(href).status_code == 200, "the menu leads to a page that refuses him"


# ── the notice for an address that says nobody ──────────────────────────────


def _double(db, email: str, *, same_household: bool = False, mixed: bool = False):
    """Two persons with one confirmed address, written as rows from before the
    rule were: two households, one household (allowed), or one of each."""
    now = datetime.now(timezone.utc)
    first, second = Member(), Member()
    db.add_all([first, second])
    db.flush()
    one = create_test_person(db, first_name="Een", last_name="Dubbel-1740")
    two = create_test_person(db, first_name="Twee", last_name="Dubbel-1740")
    db.add(MemberPerson(member_id=first.id, person_id=one.id, relation_type="HOOFDLID"))
    if same_household:
        db.add(MemberPerson(member_id=first.id, person_id=two.id, relation_type="PARTNER"))
    elif not mixed:
        db.add(MemberPerson(member_id=second.id, person_id=two.id, relation_type="HOOFDLID"))
    for person in (one, two):
        db.add(
            ContactDetail(
                person_id=person.id,
                contact_type_code="EMAIL",
                value=email,
                is_primary=True,
                confirmed_at=now,
            )
        )
    db.commit()
    return one, two


def test_the_notice_has_one_text_for_every_address_that_says_nobody(client, db_session, sent):
    _double(db_session, "gemengd-1740@example.org", mixed=True)
    step = client.post("/aanmelden", data={"email": "gemengd-1740@example.org"})
    assert "We stuurden een code naar dit adres." in step.text
    assert sent == [], "the request itself sends nothing; the notice waits in the queue"
    run_due_jobs(db_session)
    (mail,) = sent
    assert mail["type"] == "member_contact_notice"
    body = re.sub(r"\s+", " ", mail["body"])
    assert "dit e-mailadres is bij meer dan één persoon gekend" in body
    assert "kunnen we niet bepalen wie je bent" in body
    assert "Neem contact op met het bestuur" in body
    assert "gezinnen" not in body and "gezin " not in body


# ── Personen: the badge ─────────────────────────────────────────────────────


def _status(html: str, person) -> str:
    row = html[html.index(f'data-person="{person.id}"') :].split("</tr>")[0]
    return row[row.index('data-cell="status"') :].split("</td>")[0]


def _personen(client) -> str:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    assert csrf_token_for(value)
    return client.get("/admin/personen", params={"zicht": "alle", "q": "Dubbel-1740"}).text


@pytest.mark.parametrize("mixed", [False, True])
def test_personen_marks_both_holders_of_a_double_address(client, db_session, mixed):
    one, two = _double(db_session, "dubbel-1740@example.org", mixed=mixed)
    html = _personen(client)
    for person in (one, two):
        status = _status(html, person)
        assert "data-double-email" in status and "dubbel e-mailadres" in status, status
        assert ">Account<" not in status.replace("\n", ""), "an address that signs nobody in"
    assert ">Gezin<" in _status(html, one).replace("\n", ""), "the badge replaced Gezin"
    assert (">Gezin<" in _status(html, two).replace("\n", "")) is (not mixed)
    assert html.count("data-double-email") == 2


def test_two_members_of_one_household_who_share_an_address_are_not_double(client, db_session):
    one, two = _double(db_session, "gedeeld-1740@example.org", same_household=True)
    html = _personen(client)
    for person in (one, two):
        status = _status(html, person)
        assert "data-double-email" not in status and "dubbel" not in status
        assert ">Gezin<" in status.replace("\n", "")

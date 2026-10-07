"""The landing page "Mijn <site>" and the account menu (CR-22 S3, #1706; R13,
R14, R26; C6 T18).

- the page is the signed-in person's: without a session it asks to sign in and
  comes back;
- **a member sees the SAME membership card as Mijn gezin** — one partial, so the
  two pages render the same `data-membership-status` block (T18);
- the account menu is one list: the landing page first, called "Mijn " + the
  site's name, then the modules' items; the page's own menu marks where you are;
- where the tenant has no members there is no card and no "Mijn gezin".

Red (each restored after): the include of `_membership_card.html` taken out of
`account_home.html` → the card test; `aria-current` taken out of
`account_page` → the menu test; `account_nav` given a fixed "Mijn Raak" → the
site-name test.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm import tenant_lookup
from app.domains.mdm.api import Organization, invalidate_tenant_codes
from app.kernel.modules import ModuleCode
from app.kernel.tenancy import TENANT_MILLEGEM_ID
from app.kernel.tenant_config import _actieve_tenant
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

EMAIL = "lid-1706@example.org"


def _main(html: str) -> str:
    return html[html.index('<main id="main"') : html.index("</main>")]


def _card(html: str) -> str:
    """The membership card: from its hook to the end of its section."""
    main = _main(html)
    start = main.index("data-membership-status")
    return main[main.rfind("<section", 0, start) : main.index("</section>", start)]


@pytest.fixture
def member(client, db_session):
    _household, person = create_test_family(db_session, email=EMAIL)
    person.first_name, person.last_name = "Emma", "Voorbeeld"
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(EMAIL))
    return person


def test_without_a_session_the_page_asks_to_sign_in_and_comes_back(client):
    response = client.get("/mijn", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/aanmelden?terug=/mijn"


def test_a_member_lands_on_a_page_named_after_the_site(client, member):
    response = client.get("/mijn")
    assert response.status_code == 200
    main = _main(response.text)
    assert re.search(r"<h1 data-page-title[^>]*>\s*Mijn Raak Millegem\s*</h1>", main)
    assert "Dag Emma." in main


def test_the_title_follows_the_sites_own_name(client, db_session, member):
    organisation = (
        db_session.query(Organization)
        .filter(Organization.id == _actieve_tenant(None))
        .execution_options(include_all_tenants=True)
        .one()
    )
    organisation.site_name = "Voorbeeldafdeling"
    db_session.commit()
    html = client.get("/mijn").text
    assert re.search(r"<h1 data-page-title[^>]*>\s*Mijn Voorbeeldafdeling\s*</h1>", _main(html))
    assert "Mijn Raak" not in html


def test_a_member_sees_the_same_membership_card_as_on_mijn_gezin(client, db_session, member):
    """T18: one partial, two places — the blocks are the same HTML, and they say
    what the card's view-model says."""
    from app.domains.membership.api import membership_card
    from app.ui import templates

    landing = _card(client.get("/mijn").text)
    household = _card(client.get("/leden/gezin").text)
    assert "data-membership-status" in landing and "Lidmaatschap" in landing
    assert landing.split() == household.split(), "the two pages render another card"
    card = membership_card(db_session, member)
    if card.valid_until is None:
        assert "geen geldig lidmaatschap" in landing and "data-membership-valid" not in landing
    else:
        assert templates.env.filters["kortedatum"](card.valid_until) in landing


def test_the_pages_menu_is_the_account_menu_and_marks_where_you_are(client, member):
    main = _main(client.get("/mijn").text)
    menu = main[main.index("data-account-page-menu") : main.index("</nav>")]
    rows = re.findall(r'<a href="([^"]+)" class="site-drawer-row"([^>]*)>(.*?)</a>', menu, re.S)
    assert [href for href, _attrs, _body in rows] == ["/mijn", "/mijn/gegevens", "/leden/gezin"]
    assert 'aria-current="page"' in rows[0][1]
    assert all("aria-current" not in attrs for _href, attrs, _body in rows[1:])
    assert all(body.count("<svg") == 1 for _href, _attrs, body in rows)
    # No heading above the menu: its first item carries the page's title (Q35).
    assert "<h2" not in menu and "<h3" not in menu and "Mijn Raak Millegem" in rows[0][2]
    # On a phone the same items stand as links at the bottom — without the page itself.
    links = main[main.index("data-account-links") :]
    links = links[: links.index("</nav>")]
    assert re.findall(r'<a href="([^"]+)"', links) == ["/mijn/gegevens", "/leden/gezin"]
    assert (
        "md:hidden"
        in main[main.index("data-account-links") - 200 : main.index("data-account-links") + 200]
    )


def test_nothing_about_registrations_stands_on_the_page_yet(client, member):
    """T18, the last part: no registration → no "Je laatste inschrijving" card
    (and none at all before S5)."""
    assert "laatste inschrijving" not in _main(client.get("/mijn").text).lower()


def test_a_tenant_without_members_has_no_card_and_no_household_item(client, member, monkeypatch):
    invalidate_tenant_codes()
    without = frozenset(code.value for code in ModuleCode) - {ModuleCode.MEMBERSHIP.value}
    monkeypatch.setattr(tenant_lookup, "_modules_cache", {TENANT_MILLEGEM_ID: without})
    try:
        html = client.get("/mijn").text
    finally:
        invalidate_tenant_codes()
    main = _main(html)
    assert "data-membership-status" not in main
    assert "/leden/gezin" not in main


def _account_items(html: str, block: str) -> list[str]:
    """What the account menu holds — "member" per account item, "admin",
    "sign-out" — in the header's menu or the drawer."""
    start = html.index(block)
    end = html.index("</div>", start)
    return re.findall(r'data-account-item="([a-z-]+)"', html[start:end])


def _board_user(db, email: str) -> None:
    from app.domains.auth.api import User, UserRole

    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()


def test_the_three_kinds_of_session_and_what_each_has(client, db_session):
    """Koen, 7 October 2026 (the answer on #1706): a member has the account menu
    and the page; a member who is also a board user keeps "Admin" beside them;
    a board user who is no person here has neither the menu nor the page — his
    menu stays Admin · Uitloggen.

    Red: `account_home` sending a session without a person to the sign-in → the
    third case answers 302 where 404 is asked; the `is_member` condition taken
    out of `_site_account.html` → the third menu gains two items."""
    create_test_family(db_session, email="alleen-lid-1706@example.org")
    create_test_family(db_session, email="lid-en-bestuur-1706@example.org")
    _board_user(db_session, "lid-en-bestuur-1706@example.org")
    _board_user(db_session, "alleen-bestuur-1706@example.org")
    seen = {}
    for kind, email in (
        ("member", "alleen-lid-1706@example.org"),
        ("member and board", "lid-en-bestuur-1706@example.org"),
        ("board without a person", "alleen-bestuur-1706@example.org"),
    ):
        client.cookies.set(SESSION_COOKIE, make_session_value(email))
        home = client.get("/").text
        page = client.get("/mijn", follow_redirects=False)
        seen[kind] = (
            _account_items(home, "data-account-menu"),
            _account_items(home, "data-drawer-account"),
            page.status_code,
        )
    assert seen["member"] == (["member"] * 3 + ["sign-out"],) * 2 + (200,)
    assert seen["member and board"] == (["member"] * 3 + ["admin", "sign-out"],) * 2 + (200,)
    assert seen["board without a person"] == (["admin", "sign-out"],) * 2 + (404,)


def test_the_browser_title_is_the_page_and_the_site(client, member):
    """Koen, 7 October 2026: the one form, "<page> · <site name>" — no exception
    for a page whose own name holds the site's."""
    html = client.get("/mijn").text
    title = re.search(r"<title>(?:\[\w+\] )?(.*?)</title>", html, re.S).group(1).strip()
    assert title == "Mijn Raak Millegem · Raak Millegem"

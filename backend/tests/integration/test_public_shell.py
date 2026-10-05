"""CR-11 pilot B, P1 (#1588) — the public shell: the account menu, the footer's
row and the legal line.

Block 11 (Koen, 4 October 2026; `docs/design-system-end-state.md` §2.5):

- **the account**: the member's first name opens ONE menu — Mijn gezin · Admin ·
  Uitloggen; "Admin" only for who the back office admits; without a session
  "Inloggen" stands in its place; the drawer carries the same items;
- **the footer's row**: the newsletter's call (it left the home page), the
  social links, the sponsors — a column without content goes with its heading;
- **the legal line** carries the organisation's details, each ONCE, from the
  organisation the site shows; a detail that is not filled in leaves no empty
  separator;
- **the CMS block `site-footer` is no longer rendered** (it stays as data).

What only a browser shows — the header's heights, the drawer over the page with
its focus kept inside, the sticky header under a banner that scrolls away — is
in `tests_e2e/test_public_shell.py`.

Proven red (each on this branch, restored after):
- "Admin" rendered for every signed-in visitor → the admin-item test fails;
- the drawer given a list of its own without "Admin" → the same-items test fails;
- the organisation block put back above the legal line → the once test fails;
- a part without a value kept in `legal_parts` → the missing-address test fails;
- the `site-footer` block rendered again → the block test fails;
- the newsletter link put back on the home page → the newsletter test fails.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.cms.api import CmsPage
from app.domains.mdm.api import Address, BankAccount, ContactDetail, Organization, PostalCode
from app.kernel.tenant_config import _actieve_tenant
from app.ui import legal_parts
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

TENANT = _actieve_tenant(None)


def _organisation(db):
    return (
        db.query(Organization)
        .filter(Organization.id == TENANT)
        .execution_options(include_all_tenants=True)
        .one()
    )


def _contact(db, organisation, code: str, value: str) -> None:
    db.add(
        ContactDetail(
            tenant_id=TENANT, organization_id=organisation.id, contact_type_code=code, value=value
        )
    )


@pytest.fixture
def details(db_session):
    """The organisation with an address, an e-mail address, a phone number and
    an account number — invented."""
    organisation = _organisation(db_session)
    pc = db_session.query(PostalCode).first()
    if pc is None:
        pc = PostalCode(postal_code="2400", municipality="Mol")
        db_session.add(pc)
        db_session.flush()
    _contact(db_session, organisation, "EMAIL", "bestuur@example.com")
    _contact(db_session, organisation, "PHONE", "014 00 00 00")
    db_session.add(BankAccount(organization_id=organisation.id, iban="BE68 5390 0754 7034"))
    db_session.add(
        Address(
            tenant_id=TENANT,
            organization_id=organisation.id,
            street="Kerkstraat",
            house_number="12",
            postal_code_id=pc.id,
        )
    )
    db_session.commit()
    return {"organisation": organisation, "town": pc.municipality, "postal": pc.postal_code}


def _user(db, email: str, *roles: str) -> str:
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role_code=role))
    db.commit()
    return email


def _home(client, email: str | None = None) -> str:
    if email:
        client.cookies.set(SESSION_COOKIE, make_session_value(email))
    response = client.get("/")
    assert response.status_code == 200
    return response.text


def _footer(html: str) -> str:
    return html[html.index('<footer class="site-footer"') : html.index("</footer>")]


def _legal(html: str) -> str:
    line = re.search(r"<p class=\"site-legal[^>]*data-footer-line>(.*?)</p>", html, re.S).group(1)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", line)).strip()


def _items(block: str) -> list[str]:
    return re.findall(r'data-account-item="([a-z-]+)"', block)


def _menu(html: str) -> str:
    return html[html.index("data-account-menu") : html.index("data-menu-button")]


def _drawer(html: str) -> str:
    return html[html.index("data-drawer-account") : html.index('<main id="main"')]


# ── the account ──────────────────────────────────────────────────────────────


def test_signed_out_the_header_says_inloggen_and_nothing_else(client):
    html = _home(client)
    account = html[html.index("data-site-account") : html.index("data-menu-button")]
    assert "data-sign-in" in account and ">Inloggen<" in account
    assert "data-account-button" not in html and _items(html) == []
    # The drawer too.
    assert "data-sign-in" in _drawer(html) and "Inloggen" in _drawer(html)


def test_a_member_sees_the_first_name_and_mijn_gezin(client, db_session):
    _member, person = create_test_family(db_session, email="lid-1588@example.org")
    person.first_name, person.last_name = "Emma", "Voorbeeld"
    db_session.commit()
    html = _home(client, "lid-1588@example.org")
    button = re.search(r"<button[^>]*data-account-button.*?</button>", html, re.S).group(0)
    # The first name on the button, the full name in the menu.
    assert ">Emma<" in button and "Voorbeeld" not in button
    assert "Emma Voorbeeld" in _menu(html)
    assert _items(_menu(html)) == ["member", "sign-out"]
    assert re.search(r'href="[^"]*/leden/gezin"[^>]*data-account-item="member"', _menu(html))
    # No way into the back office for a member, in neither place.
    assert 'href="/admin"' not in html


@pytest.mark.parametrize("role", ["ADMIN", "OPERATOR"])
def test_admin_stands_in_the_menu_for_who_the_back_office_admits(client, db_session, role):
    email = _user(db_session, f"{role.lower()}-1588@example.org", role)
    html = _home(client, email)
    assert _items(_menu(html)) == ["admin", "sign-out"]
    admin = re.search(r"<a[^>]*data-account-item=\"admin\"[^>]*>", _menu(html)).group(0)
    # A way out of the boosted public shell, as before.
    assert 'href="/admin"' in admin and 'hx-boost="false"' in admin
    # One menu: no separate Admin link beside it in the header's row.
    row = html[html.index('id="site-nav-breed"') : html.index("data-site-account")]
    assert "/admin" not in row


def test_another_role_gets_no_admin_item(client, db_session):
    email = _user(db_session, "finance-1588@example.org", "FINANCE")
    html = _home(client, email)
    assert _items(_menu(html)) == ["sign-out"] and 'href="/admin"' not in html


def test_the_drawer_carries_the_same_items_as_the_menu(client, db_session):
    _member, person = create_test_family(db_session, email="bestuur-1588@example.org")
    person.first_name = "Bram"
    db_session.commit()
    email = "bestuur-1588@example.org"
    user = User(email=email, is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db_session.commit()
    html = _home(client, email)
    assert _items(_menu(html)) == ["member", "admin", "sign-out"]
    assert _items(_drawer(html)) == _items(_menu(html))
    # One source for both (`_site_account.html`): the same addresses too.
    hrefs = lambda block: re.findall(r'<a href="([^"]+)"[^>]*data-account-item', block)  # noqa: E731
    assert hrefs(_drawer(html)) == hrefs(_menu(html))


# ── the footer ───────────────────────────────────────────────────────────────


def test_the_legal_line_carries_the_organisations_details_once(client, db_session, details):
    html = _home(client)
    footer = _footer(html)
    assert _legal(html).endswith(
        f"· Kerkstraat 12, {details['postal']} {details['town']} · bestuur@example.com · "
        "014 00 00 00 · BE68 5390 0754 7034"
    )
    assert re.findall(r'data-legal="([a-z]+)"', footer) == ["address", "email", "phone", "iban"]
    # Each detail stands ONCE on the page: no separate contact block above it.
    for value in ("Kerkstraat 12", "bestuur@example.com<", "014 00 00 00", "BE68 5390 0754 7034"):
        assert html.count(value) == 1, value
    assert "Rekeningnummer" not in footer
    # The e-mail address and the phone number are links.
    assert 'href="mailto:bestuur@example.com" data-legal="email"' in footer
    assert 'href="tel:014000000" data-legal="phone"' in footer


def test_a_detail_that_is_not_filled_in_leaves_no_empty_separator(client, db_session):
    """PROD's organisation has contact details and no address (measured,
    4 October 2026): the line then simply says what there is."""
    organisation = _organisation(db_session)
    _contact(db_session, organisation, "EMAIL", "bestuur@example.com")
    db_session.commit()
    line = _legal(_home(client))
    assert line.endswith("· bestuur@example.com")
    assert "· ·" not in line and not line.endswith("·")
    # The unit: only what has a value, in the fixed order.
    assert legal_parts(None) == []
    parts = legal_parts(
        {"address_lines": [], "email": None, "phone": "014 00 00 00", "iban": "BE00", "bic": "ABCD"}
    )
    assert [(p["kind"], p["text"]) for p in parts] == [
        ("phone", "014 00 00 00"),
        ("iban", "BE00 (ABCD)"),
    ]


def test_the_site_footer_block_is_no_longer_rendered(client, db_session):
    """The free CMS block held what the organisation's details hold now; it
    stays as data and reaches no page."""
    block = db_session.query(CmsPage).filter(CmsPage.slug == "site-footer").one_or_none()
    if block is None:
        block = CmsPage(title="Voettekst", slug="site-footer", show_in_nav=False)
        db_session.add(block)
    block.content = "<p>VRIJE-VOETTEKST-1588</p>"
    block.is_published = True
    db_session.commit()
    assert "VRIJE-VOETTEKST-1588" not in _home(client)
    db_session.refresh(block)
    assert "VRIJE-VOETTEKST-1588" in block.content


def test_the_newsletter_call_stands_in_the_footer_of_every_page_and_not_on_the_home(
    client, db_session, details
):
    html = _home(client)
    footer = _footer(html)
    section = footer[footer.index("data-footer-newsletter") :]
    # #1606 (Koen, 5 October 2026): "Nieuws van <the site's name>" — also where
    # the organisation has a town; P1's "Nieuws uit <plaats>" is gone.
    from app.kernel.tenant_config import tenant_display_name

    assert f"Nieuws van {tenant_display_name(db_session)}" in section
    assert "Nieuws uit" not in html
    call = re.search(r'<a id="nb-voet-link"[^>]*>(.*?)</a>', section, re.S)
    assert call and call.group(1).strip() == "Aanmelden"
    assert re.search(r'id="nb-voet-link" href="[^"]*/nieuwsbrief"', section)
    # Once, and only in the footer: the home page's own link is gone.
    assert html.count('/nieuwsbrief"') == 1 and "nb-home-link" not in html
    # Another public page carries it too.
    other = client.get("/activiteiten").text
    assert "nb-voet-link" in _footer(other)


def test_the_newsletter_names_the_site_also_without_a_town(client, db_session):
    from app.kernel.tenant_config import tenant_display_name

    name = tenant_display_name(db_session)
    assert f"Nieuws van {name}" in _footer(_home(client))


def test_a_column_without_content_goes_with_its_heading(client, db_session):
    footer = _footer(_home(client))
    # The seeded tenant has no social links and no sponsors.
    assert "data-footer-social" not in footer and "data-footer-sponsors" not in footer
    assert "Volg ons" not in footer and "Met steun van" not in footer
    organisation = _organisation(db_session)
    _contact(db_session, organisation, "FACEBOOK", "https://www.facebook.com/voorbeeld")
    db_session.commit()
    footer = _footer(_home(client))
    social = footer[footer.index("data-footer-social") :]
    assert "Volg ons" in social and 'href="https://www.facebook.com/voorbeeld"' in social
    # An icon of 24 px in a target of 44 px.
    assert 'class="w-6 h-6"' in social and "w-11 h-11" in social


def test_the_header_and_the_footer_share_one_container(client):
    html = _home(client)
    assert html.count('class="site-container') == 3  # header, main, footer
    assert '<main id="main" class="site-container' in html

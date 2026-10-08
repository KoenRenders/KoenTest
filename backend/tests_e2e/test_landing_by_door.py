"""E2E: a board member signs in on the public site and stays on it (#1740;
Koen, 8 October 2026: "waar men aanlogt komt men terecht").

At 390 px: a board member who is a member too opens the menu, taps
"Inloggen", asks his code and signs in through the link of the mail. He
stands on "Mijn <tenant>" — not in the back office — and "Admin" is in his
menu, leading to the back office's start page.

The test makes its own household and board account and removes them again.

On master the link lands him on `/admin/werkbank`.
"""

import os
import sys
import uuid
from datetime import date

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def board_member():
    """A main member of a household who holds ADMIN too."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import User, UserRole
    from app.domains.mdm.api import Member, MemberPerson, Person, new_contact_detail
    from app.soft_delete import soft_delete

    tag = uuid.uuid4().hex[:8]
    email = f"bestuurslid-{tag}@example.org"
    db = SessionLocal()
    try:
        member = Member()
        db.add(member)
        db.flush()
        person = Person(
            first_name="Bo",
            last_name=f"Bestuur-{tag}",
            date_of_birth=date(1980, 1, 1),
            gender_code="M",
        )
        db.add(person)
        db.flush()
        db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type="HOOFDLID"))
        db.flush()
        db.add(new_contact_detail(db, person, "EMAIL", email, is_primary=True))
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
        db.commit()
        made = {"email": email, "member": member.id, "person": person.id, "user": user.id}
    finally:
        db.close()
    yield made
    db = SessionLocal()
    try:
        for role in db.query(UserRole).filter(UserRole.user_id == made["user"]).all():
            db.delete(role)
        user = db.query(User).filter(User.id == made["user"]).first()
        if user is not None:
            user.is_active = False
        person = db.query(Person).filter(Person.id == made["person"]).first()
        if person is not None:
            for row in [*person.contact_details, *person.member_persons]:
                soft_delete(row)
            soft_delete(person)
        member = db.query(Member).filter(Member.id == made["member"]).first()
        if member is not None:
            soft_delete(member)
        db.commit()
    finally:
        db.close()


def _mail_link(email: str) -> str:
    """The link of the sign-in mail: the token the request just made."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import LoginToken

    db = SessionLocal()
    try:
        token = db.query(LoginToken).filter_by(email=email, used=False).one()
        return f"/login/verify?token={token.token}"
    finally:
        db.close()


def test_a_board_member_who_signs_in_on_the_site_stays_on_the_site(browser, board_member):
    page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        page.goto("/")
        pagina_klaar(page)
        page.locator("[data-menu-button]").click()
        drawer = page.locator("[data-drawer-account]")
        drawer.get_by_role("link", name="Inloggen").click()
        page.wait_for_url(lambda url: "/aanmelden" in url)
        pagina_klaar(page)
        page.locator('#aanmelden-stap input[name="email"]').fill(board_member["email"])
        with htmx_afgerond(page):
            page.locator("#aanmelden-stap button").click()
        expect(page.locator("[data-code-sent]")).to_be_visible()

        page.goto(_mail_link(board_member["email"]))
        pagina_klaar(page)
        path = page.url.replace(BASE, "")
        title = page.locator("#main h1").inner_text().strip()
        print("MEASURE landing by door 390:", path, "|", title)
        assert path == "/mijn", f"landed on {path}"
        assert title.startswith("Mijn "), title

        page.locator("[data-menu-button]").click()
        expect(drawer).to_be_visible()
        admin = drawer.locator('[data-account-item="admin"]')
        expect(admin).to_have_text("Admin")
        assert admin.get_attribute("href") == "/admin"
        items = [i.strip() for i in drawer.locator("[data-account-item]").all_inner_texts()]
        print("MEASURE landing by door 390, menu:", items)
        assert items[-2:] == ["Admin", "Uitloggen"], items
        wide = page.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
        assert wide[0] == wide[1], "wider than the window"
    finally:
        page.close()

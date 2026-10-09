"""E2E: a waiting e-mail address on the household record of the back office
(#1733; CR-22 R15).

At 1440 and at 390 px, the person card in edit: the waiting row carries the
badge "wacht op bevestiging" INSIDE the row and no "Maak hoofdadres"; the
confirmed second address carries the button; nothing is wider than the window.

The test makes its own household — a main address, a confirmed second one and
one that waits — and removes it again.

On master the waiting row shows "Maak hoofdadres" and no badge.
"""

import os
import sys
import uuid

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def household():
    """A household of one, with three addresses: main, confirmed, waiting."""
    from datetime import date

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import Member, MemberPerson, Person, new_contact_detail
    from app.soft_delete import soft_delete

    tag = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        member = Member()
        db.add(member)
        db.flush()
        person = Person(
            first_name="Wies",
            last_name=f"Wachter-{tag}",
            date_of_birth=date(1980, 1, 1),
            gender_code="F",
        )
        db.add(person)
        db.flush()
        db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type="HOOFDLID"))
        db.flush()
        for name, primary, confirmed in (
            ("hoofd", True, True),
            ("tweede", False, True),
            ("wacht", False, False),
        ):
            db.add(
                new_contact_detail(
                    db,
                    person,
                    "EMAIL",
                    f"{name}-{tag}@example.org",
                    is_primary=primary,
                    confirmed=confirmed,
                )
            )
        db.commit()
        made = {"member": member.id, "person": person.id, "tag": tag}
    finally:
        db.close()
    yield made
    db = SessionLocal()
    try:
        person = db.query(Person).filter(Person.id == made["person"]).first()
        if person is not None:
            for contact in person.contact_details:
                soft_delete(contact)
            for link in person.member_persons:
                soft_delete(link)
            soft_delete(person)
        member = db.query(Member).filter(Member.id == made["member"]).first()
        if member is not None:
            soft_delete(member)
        db.commit()
    finally:
        db.close()


ROWS = """(person) => { const card = document.querySelector('#persoon-' + person);
  const rows = [...card.querySelectorAll('[data-email-rij]')].filter(r => r.checkVisibility());
  return {rows: rows.map(r => { const box = r.getBoundingClientRect(), badge = r.querySelector('[data-email-waiting]');
      const b = badge ? badge.getBoundingClientRect() : null;
      return {address: r.querySelector('input[type=email]').value,
              waiting: !!badge && badge.checkVisibility(),
              inside: b ? (b.left >= box.left - 0.5 && b.right <= box.right + 0.5 && b.top >= box.top - 0.5 && b.bottom <= box.bottom + 0.5) : null,
              buttons: [...r.querySelectorAll('button')].filter(x => x.checkVisibility()).map(x => x.innerText.trim())}; }),
    page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (390, 844)])
def test_a_waiting_row_carries_the_mark_and_no_main_address_button(
    browser, household, width, height
):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    try:
        login_als_admin(page, email, make_session_value(email))
        page.goto(f"/admin/leden/gezin/{household['member']}")
        pagina_klaar(page)
        card = page.locator(f"#persoon-{household['person']}")
        card.get_by_role("button", name="Bewerken").click()
        card.locator("[data-email-rij]").first.wait_for(state="visible")
        found = page.evaluate(ROWS, household["person"])
        print("MEASURE pending address board", width, found)
        rows = {r["address"].split("-")[0]: r for r in found["rows"]}
        assert set(rows) == {"hoofd", "tweede", "wacht"}, found
        assert rows["wacht"]["waiting"] and rows["wacht"]["inside"], (
            "the mark is not inside its row"
        )
        assert rows["wacht"]["buttons"] == ["Verwijderen"], rows["wacht"]
        assert not rows["tweede"]["waiting"]
        assert rows["tweede"]["buttons"] == ["Maak hoofdadres", "Verwijderen"], rows["tweede"]
        assert not rows["hoofd"]["waiting"] and rows["hoofd"]["buttons"] == ["Verwijderen"]
        assert found["page"][0] == found["page"][1], "wider than the window"
    finally:
        page.close()

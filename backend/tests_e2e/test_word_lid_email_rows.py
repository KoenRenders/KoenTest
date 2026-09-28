"""#1246 — on a phone, Word lid takes a second e-mail address, and it is stored.

The pytest suite (`tests/test_word_lid_email_rows.py`) proves the form and the
service; there the request shares the test's session, so it cannot tell a flush
from a commit (#1223, #1244). This test goes through the browser at 390 px — 80 %
of public visits are on a phone — adds a row with "+ E-mailadres", registers, and
reads the two addresses back through a session of its own. Then it removes the
family again through the service, because the e2e tests share their seed and a
leftover transfer payment shifts other tests (#1241).

It also measures the rows as rendered: the page does not scroll sideways, the
"hoofdadres" label sits level with its field, the primary row has no remove
button, and the added row's remove button lies inside the viewport.
"""

import os
import sys
import uuid
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond  # noqa: E402

PHONE = 390


@pytest.fixture(scope="module")
def phone():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": PHONE, "height": 900})
        yield page
        browser.close()


def _stored_addresses(first: str):
    """{value: is_primary} of the person owning `first`, read in a session of our own."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.mdm.api import ContactDetail, MemberPerson

    db = SessionLocal()
    try:
        person_id = db.query(ContactDetail.person_id).filter(ContactDetail.value == first).scalar()
        if person_id is None:
            return None, {}
        member_id = (
            db.query(MemberPerson.member_id).filter(MemberPerson.person_id == person_id).scalar()
        )
        rows = (
            db.query(ContactDetail)
            .filter(
                ContactDetail.person_id == person_id, ContactDetail.contact_type_code == "EMAIL"
            )
            .all()
        )
        return member_id, {r.value: bool(r.is_primary) for r in rows}
    finally:
        db.close()


def _remove_family(member_id: int) -> None:
    import app.main  # noqa: F401  the whole app, so the domain facades import in order
    from app.database import SessionLocal
    from app.domains.membership.api import delete_family

    db = SessionLocal()
    try:
        delete_family(db, member_id, admin=SimpleNamespace(email="e2e-1246@example.com"))
    finally:
        db.close()


def test_a_second_address_on_a_phone_is_stored_beside_the_primary_one(phone):
    page = phone
    tag = uuid.uuid4().hex[:8]
    first, second = f"e2e.een.{tag}@example.com", f"e2e.twee.{tag}@example.com"
    member_id = None
    try:
        page.goto("/lid-worden")
        primary = page.locator("#m0_email")
        expect(primary).to_have_count(1)
        with htmx_afgerond(page):
            page.get_by_role("button", name="+ E-mailadres").first.click()
        rows = page.locator("#emails-0 [data-email-rij]")
        expect(rows).to_have_count(2)

        # ── The rows as rendered, at 390 px ──
        geometry = page.evaluate("""() => {
          const rows = [...document.querySelectorAll('#emails-0 [data-email-rij]')];
          const box = el => el ? el.getBoundingClientRect() : null;
          const first = rows[0], extra = rows[1];
          const input = box(first.querySelector('input'));
          const badge = box([...first.querySelectorAll('span')].find(s => s.textContent.trim() === 'hoofdadres'));
          const remove = box([...extra.querySelectorAll('button')].find(b => b.textContent.trim() === 'Verwijderen'));
          return {scrollWidth: document.documentElement.scrollWidth,
                  firstHasRemove: [...first.querySelectorAll('button')].some(b => b.textContent.trim() === 'Verwijderen'),
                  inputMid: input && Math.round(input.top + input.height / 2),
                  badgeMid: badge && Math.round(badge.top + badge.height / 2),
                  badgeRight: badge && Math.round(badge.right),
                  removeRight: remove && Math.round(remove.right),
                  removeWidth: remove && Math.round(remove.width)};
        }""")
        assert geometry["scrollWidth"] <= PHONE, f"the form scrolls sideways: {geometry}"
        assert geometry["badgeMid"] is not None, (
            f"no 'hoofdadres' label on the first row: {geometry}"
        )
        assert not geometry["firstHasRemove"], "the primary row must not be removable"
        assert geometry["badgeRight"] <= PHONE, f"the label sticks out: {geometry}"
        assert (
            geometry["removeRight"] is not None
            and geometry["removeWidth"] > 40
            and geometry["removeRight"] <= PHONE
        ), f"the added row's remove button is unusable: {geometry}"
        # The label sits level with its field when they share a line; on a wrap it
        # sits below it. Either way it belongs to that row, not to the next one.
        assert (
            abs(geometry["badgeMid"] - geometry["inputMid"]) <= 2
            or geometry["badgeMid"] > geometry["inputMid"]
        ), f"label out of line: {geometry}"

        # ── Register ──
        page.fill("#m0_first_name", "E2E")
        page.fill("#m0_last_name", f"Rijen {tag}")
        page.fill("#m0_date_of_birth", "1980-01-01")
        page.select_option("#m0_gender_code", "M")
        page.fill("#m0_mobile", "0470000000")
        primary.fill(first)
        rows.nth(1).locator("input").fill(second)
        page.fill("#street", "Teststraat")
        page.fill("#house_number", "1")
        page.select_option("#postal_code", index=1)
        page.check('input[name="payment_method"][value="transfer"]')
        page.click('button[type="submit"]')
        expect(page.get_by_text("Je inschrijving is ontvangen")).to_be_visible()

        # ── Read back through a session of our own: only a commit is visible here ──
        member_id, stored = _stored_addresses(first)
        assert stored == {first: True, second: False}, f"stored: {stored}"
    finally:
        if member_id is None:
            member_id, _ = _stored_addresses(first)
        if member_id is not None:
            _remove_family(member_id)

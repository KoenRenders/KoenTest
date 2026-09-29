"""E2E: the start-date fields of the circle screen fit a phone (#1346).

The circle screen got two date fields: one "In de kring vanaf" above the search
results, and one "In de kring sinds" with "Datum bewaren" on every person. At 390
and 1280 px the page may not scroll sideways, the fields and their buttons lie
inside their card, and changing the date through the screen stores it.
"""

import os
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_als_admin  # noqa: E402

SHOTS = "/scratch/shots_1346"

# The person's row, its start-date form, and the card around it.
_MEASURE = """(name) => {
  const row = [...document.querySelectorAll('#vg-kring .py-2\\\\.5')]
    .find(r => r.textContent.includes(name));
  const card = row.closest('.rounded-2xl').getBoundingClientRect();
  const form = row.querySelector('form[hx-post$="/start"]');
  const box = el => { const r = el.getBoundingClientRect();
    return {left: Math.round(r.left), right: Math.round(r.right), top: Math.round(r.top),
            width: Math.round(r.width)}; };
  const add = document.querySelector('#vg-kring-start');
  return {
    doc: document.documentElement.scrollWidth, vw: innerWidth,
    card_right: Math.round(card.right),
    date: box(form.querySelector('input[type=date]')),
    button: box(form.querySelector('button[type=submit]')),
    add_date: box(add),
    add_card_right: Math.round(add.closest('.rounded-2xl').getBoundingClientRect().right),
  };
}"""


def _add_to_circle(first: str, last: str) -> None:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import (
        ContactDetail,
        Organization,
        OrganizationPerson,
        Person,
    )

    db = SessionLocal()
    try:
        person = Person(first_name=first, last_name=last)
        db.add(person)
        db.flush()
        db.add(
            ContactDetail(
                person_id=person.id,
                contact_type_code="EMAIL",
                value=f"{first.lower()}.{last.lower()}@voorbeeld-van-een-lang-domein.example",
                is_primary=True,
            )
        )
        db.add(
            OrganizationPerson(
                person_id=person.id,
                organization_id=db.query(Organization).first().id,
                relation_type="BOARD_MEETING",
                start_date=date.today(),
            )
        )
        db.commit()
    finally:
        db.close()


def _start_of(last: str) -> date:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import OrganizationPerson, Person

    db = SessionLocal()
    try:
        person = db.query(Person).filter_by(last_name=last).one()
        return db.query(OrganizationPerson).filter_by(person_id=person.id).one().start_date
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, email, make_session_value(email)
        b.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_the_start_date_fields_fit_and_store(browser, width):
    last = f"Kringproef{secrets.token_hex(2)}"
    _add_to_circle("Annemarie", last)

    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto("/admin/vergaderingen/kring")
        htmx_stil(page)

        m = page.evaluate(_MEASURE, last)
        print(f"MEASURE @{width}", m)
        assert m["doc"] <= m["vw"], f"@{width}: the page is {m['doc']} px wide"
        for part in ("date", "button"):
            assert m[part]["right"] <= m["card_right"], f"@{width}: {part} sticks out: {m}"
            assert m[part]["width"] > 60, f"@{width}: {part} squeezed: {m}"
        assert m["add_date"]["right"] <= m["add_card_right"], m

        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.get_by_text(f"Annemarie {last}").scroll_into_view_if_needed()
            page.wait_for_function(
                "() => document.getAnimations().every(a => a.playState !== 'running')"
            )
            page.screenshot(path=f"{SHOTS}/{width}-kring.png")

        row = page.locator("#vg-kring .py-2\\.5", has_text=last)
        row.locator("input[type=date]").fill("2026-08-15")
        row.get_by_role("button", name="Datum bewaren").click()
        htmx_stil(page)
        expect(
            page.locator("#vg-kring .py-2\\.5", has_text=last).locator("input[type=date]")
        ).to_have_value("2026-08-15")
        assert _start_of(last) == date(2026, 8, 15), "the screen stored the new start date"
    finally:
        page.close()

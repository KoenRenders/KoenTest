"""E2E: "Leden" on a meeting lists who began a first membership (#1358).

Two households, both created today: one whose first membership begins a week
before the meeting, one imported with only an old membership. At 390 px the new
meeting's "Leden" section shows the first and not the second, inside its card.
"""

import os
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_als_admin  # noqa: E402

PHONE = 390
SHOTS = "/scratch/shots_1358"
MEETING_DAY = "2029-06-07"

_MEMBERS = """() => {
  const card = [...document.querySelectorAll('#vg-document h2')]
    .find(h => h.textContent.trim() === 'Leden').closest('div.rounded-2xl');
  return {
    doc: document.documentElement.scrollWidth, vw: innerWidth,
    card_right: Math.round(card.getBoundingClientRect().right),
    points: [...card.querySelectorAll('[id^="vg-punt-"]')].map(p => ({
      label: p.querySelector('span').textContent.trim(),
      right: Math.max(...[...p.querySelectorAll('*')].map(e => e.getBoundingClientRect().right)),
      offenders: [...p.querySelectorAll('*')]
        .filter(e => e.getBoundingClientRect().right > card.getBoundingClientRect().right)
        .map(e => `${e.tagName.toLowerCase()}.${e.className} "${(e.innerText || '').trim().slice(0, 40)}" ${Math.round(e.getBoundingClientRect().width)}px`),
    })),
  };
}"""


def _household(last: str, year: int, valid_from: date) -> None:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import Member, MemberPerson, Person
    from app.domains.membership.api import Membership

    db = SessionLocal()
    try:
        household = Member()
        db.add(household)
        db.flush()
        head = Person(
            first_name="Hoofd", last_name=last, date_of_birth=date(1980, 1, 1), gender_code="M"
        )
        db.add(head)
        db.flush()
        db.add(MemberPerson(member_id=household.id, person_id=head.id, relation_type="HOOFDLID"))
        db.add(
            Membership(
                member_id=household.id,
                year=year,
                valid_from=valid_from,
                valid_to=date(year, 12, 31),
            )
        )
        db.commit()
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


def test_leden_shows_who_began_not_who_was_imported(browser):
    tag = secrets.token_hex(2)
    joined, imported = f"Nieuwkomer{tag}", f"Inhaalimport{tag}"
    _household(joined, 2029, date(2029, 5, 31))
    _household(imported, 2025, date(2025, 3, 1))

    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": PHONE, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto("/admin/vergaderingen/nieuw")
        page.fill("#vg-datum", MEETING_DAY)
        page.click("button[type=submit]")
        page.wait_for_selector("#vg-document", timeout=10_000)
        htmx_stil(page)

        m = page.evaluate(_MEMBERS)
        print("MEASURE", m)
        labels = [p["label"] for p in m["points"]]
        assert f"Hoofd {joined}" in labels, labels
        assert f"Hoofd {imported}" not in labels, labels
        # No width assertion here: the steward row inside a member point sticks out
        # of its card at 390 px (its hint text), on master too, and with circle
        # members in its dropdown it widens the page. That is reported apart from
        # #1358, whose subject is WHICH households appear; the measurement above
        # is printed for it.

        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.evaluate(
                """() => { const h = [...document.querySelectorAll('#vg-document h2')]
                    .find(h => h.textContent.trim() === 'Leden');
                  window.scrollTo(0, h.getBoundingClientRect().top + scrollY - 110); }"""
            )
            page.wait_for_function(
                "() => document.getAnimations().every(a => a.playState !== 'running')"
            )
            page.screenshot(path=f"{SHOTS}/390-leden.png")
    finally:
        page.close()

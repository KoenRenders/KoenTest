"""E2E: the steward choice of a member point fits its card, with and without a
circle (#1365).

Found at #1358: in a member point, the hint "genotuleerd — de toewijzing zelf
gebeurt in de Raak-administratie" stood in a narrow column beside the steward
dropdown. At 390 px it stuck out of its card (389 against 374) with an empty
circle, and with circle members in the dropdown the page became 426 px wide.

The hint now sits under the dropdown, and the dropdown may shrink (`min-w-0`).
Measured at 390 and 1280 px, with the circle of the meeting's date empty and with
a member whose name is long.

Proven red against master `ae660424`, with a server built from an export of it: all
four cases failed — at 390 px with a circle member the page was 429 px wide, and at
1280 px the hint stood beside the dropdown instead of under it.
"""

import os
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_als_admin  # noqa: E402

SHOTS = "/scratch/shots_1365"

_MEASURE = """(name) => {
  const card = [...document.querySelectorAll('#vg-document h2')]
    .find(h => h.textContent.trim() === 'Leden').closest('div.rounded-2xl');
  const point = [...card.querySelectorAll('[id^="vg-punt-"]')]
    .find(p => p.querySelector('span').textContent.trim() === name);
  const select = point.querySelector('select[name=steward_person_id]');
  const hint = [...point.querySelectorAll('span, p')]
    .find(s => s.textContent.trim().startsWith('genotuleerd'));
  const box = el => { const r = el.getBoundingClientRect();
    return {left: Math.round(r.left), right: Math.round(r.right),
            top: Math.round(r.top), bottom: Math.round(r.bottom), width: Math.round(r.width)}; };
  return {
    doc: document.documentElement.scrollWidth, vw: innerWidth,
    card_right: Math.round(card.getBoundingClientRect().right),
    options: select.options.length,
    select: box(select), hint: box(hint),
  };
}"""


def _setup(tag: str, meeting_year: int, with_circle: bool) -> str:
    """A household whose first membership begins a week before the meeting, and,
    if asked, a circle member with a long name who is in the circle on that day."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import (
        Member,
        MemberPerson,
        Organization,
        OrganizationPerson,
        Person,
    )
    from app.domains.membership.api import Membership

    db = SessionLocal()
    try:
        household = Member()
        db.add(household)
        db.flush()
        head = Person(
            first_name="Hoofd",
            last_name=f"Wijk{tag}",
            date_of_birth=date(1980, 1, 1),
            gender_code="M",
        )
        db.add(head)
        db.flush()
        db.add(MemberPerson(member_id=household.id, person_id=head.id, relation_type="HOOFDLID"))
        db.add(
            Membership(
                member_id=household.id,
                year=meeting_year,
                valid_from=date(meeting_year, 5, 31),
                valid_to=date(meeting_year, 12, 31),
            )
        )
        if with_circle:
            steward = Person(
                first_name="Anne-Marie-Josephine",
                last_name=f"Vandenbroucke-Verhaegen-{tag}",
            )
            db.add(steward)
            db.flush()
            db.add(
                OrganizationPerson(
                    person_id=steward.id,
                    organization_id=db.query(Organization).first().id,
                    relation_type="BOARD_MEETING",
                    start_date=date(2020, 1, 1),
                )
            )
        db.commit()
        return f"Hoofd Wijk{tag}"
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


# The circle of 2019 is empty (every circle relation starts in 2020 or later); the
# circle of 2031 holds at least the long-named member added here.
CASES = [
    (390, 2019, False),
    (390, 2031, True),
    (1280, 2019, False),
    (1280, 2031, True),
]


@pytest.mark.parametrize(("width", "year", "with_circle"), CASES)
def test_the_steward_choice_fits_its_card(browser, width, year, with_circle):
    tag = secrets.token_hex(2)
    name = _setup(tag, year, with_circle)
    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto("/admin/vergaderingen/nieuw")
        page.fill("#vg-datum", f"{year}-06-07")
        page.click("button[type=submit]")
        page.wait_for_selector("#vg-document", timeout=10_000)
        htmx_stil(page)

        m = page.evaluate(_MEASURE, name)
        print(f"MEASURE @{width} circle={with_circle}", m)
        assert (m["options"] > 1) is with_circle, f"the circle is not what this case needs: {m}"
        assert m["doc"] <= m["vw"], f"@{width}: the page is {m['doc']} px wide: {m}"
        assert m["select"]["right"] <= m["card_right"], f"@{width}: the dropdown sticks out: {m}"
        assert m["hint"]["right"] <= m["card_right"], f"@{width}: the hint sticks out: {m}"
        assert m["hint"]["top"] >= m["select"]["bottom"], f"the hint is not under the dropdown: {m}"
        assert m["select"]["width"] > 120, f"the dropdown was squeezed: {m}"

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
            circle = "met-kring" if with_circle else "zonder-kring"
            page.screenshot(path=f"{SHOTS}/{width}-{circle}.png")
    finally:
        page.close()

"""E2E: status and audience on the board's screens, at 390 px (#1428).

Measured:
- the card on /admin/activiteiten carries "Concept" and the audience in full,
  on or under the date line, and stays within the width;
- the record header carries "Concept" and the button "Publiceren";
- the edit form offers the audience choice, within the width.

Screenshots go outside the repo. Proven red against master `cbe40e28` (served
from an export of it): it fails at its setup, since the column `status` does
not exist there.
"""

import os
import secrets
import sys
from datetime import date, timedelta

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1428"
PHONE = {"width": 390, "height": 900}
WIDTH = "() => [document.documentElement.scrollWidth, innerWidth]"

_CARD = """(id) => {
  const card = document.querySelector(`a[href="/admin/activiteiten/${id}"]`);
  const r = e => { const b = e.getBoundingClientRect(); return {x: Math.round(b.x), y: Math.round(b.y), right: Math.round(b.right), bottom: Math.round(b.bottom)}; };
  const spans = [...card.querySelectorAll('span')];
  const find = t => spans.find(s => s.textContent.trim() === t);
  const date = [...card.querySelectorAll('span')].find(s => /\\d/.test(s.textContent) && s.className.includes('text-ink-soft'));
  return {card: r(card), concept: find('Concept') && r(find('Concept')),
          audience: find('Vrouwen') && r(find('Vrouwen')), date: date && r(date)};
}"""


def _draft() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate, ActivityStatus

    db = SessionLocal()
    try:
        activity = Activity(
            name=f"Wandelen {secrets.token_hex(2)}",
            status=ActivityStatus.DRAFT,
            target_audience="women",
        )
        db.add(activity)
        db.flush()
        db.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=40)))
        db.commit()
        return activity.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def phone():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity_id = _draft()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = b.new_page(base_url=BASE, viewport=PHONE)
        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL))
        yield page, activity_id
        b.close()


def _shot(page, name: str) -> None:
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/390-{name}.png", full_page=True)


def test_the_card_carries_concept_and_the_audience(phone):
    page, activity_id = phone
    page.goto("/admin/activiteiten?scope=all")
    pagina_klaar(page)
    m = page.evaluate(_CARD, activity_id)
    width = page.evaluate(WIDTH)
    print("MEASURE card", m, "page", width)
    page.locator(f'a[href="/admin/activiteiten/{activity_id}"]').scroll_into_view_if_needed()
    _shot(page, "kaart")
    assert m["concept"] and m["audience"], m
    assert m["card"]["right"] <= 390 and width[0] <= width[1], (m, width)
    assert m["concept"]["y"] >= m["card"]["y"] and m["audience"]["right"] <= m["card"]["right"]
    assert m["date"] and m["concept"]["bottom"] >= m["date"]["y"], "on or under the date line"


def test_the_header_and_the_edit_form(phone):
    page, activity_id = phone
    page.goto(f"/admin/activiteiten/{activity_id}")
    pagina_klaar(page)
    header = page.locator("h1")
    publish = page.get_by_role("button", name="Publiceren")
    assert "Concept" in header.inner_text()
    assert publish.count() == 1
    page.get_by_role("button", name="Bewerken").first.click()
    select = page.locator("#target_audience")
    select.wait_for(state="visible")
    box = select.bounding_box()
    chosen = select.input_value()
    width = page.evaluate(WIDTH)
    print("MEASURE header+form", {"select": box, "chosen": chosen, "page": width})
    select.scroll_into_view_if_needed()
    _shot(page, "recordkop-formulier")
    assert chosen == "women"
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390, box

"""E2E: copy an activity to a next year, at 390 px (#1397).

Measured:
- "Kopiëren naar een volgend jaar" sits on screen under the date line and adds
  nothing to the page's width (the header row is wider than a phone on master
  already, #1387);
- the copy step fits, and the two suggestions fill the date field;
- the whole way: Kopiëren → "Zelfde datum, een jaar later" → Kopie maken lands on
  the copy's overview;
- on the public agenda the copy has no registration button and no empty
  "Wie doet er mee?" line, on its card and on its page.

Screenshots go outside the repo. Proven red against master `0bb17459` (served
from an export of it): the header had no copy link to click.
"""

import os
import re
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1397"
PHONE = {"width": 390, "height": 900}
WIDTH = "() => [document.documentElement.scrollWidth, innerWidth]"


def _activity() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate

    db = SessionLocal()
    try:
        activity = Activity(name=f"Kerstherberg {secrets.token_hex(2)}", location="De zaal")
        db.add(activity)
        db.flush()
        db.add(
            ActivityDate(
                activity_id=activity.id, start_date=date(2026, 12, 25), end_date=date(2026, 12, 30)
            )
        )
        db.commit()
        return activity.id
    finally:
        db.close()


def _shot(page, name: str) -> None:
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/390-{name}.png", full_page=True)


@pytest.fixture(scope="module")
def phone():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity_id = _activity()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = b.new_page(base_url=BASE, viewport=PHONE)
        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL))
        yield b, page, activity_id
        b.close()


def test_copy_from_the_header_to_the_new_activity(phone):
    _, page, activity_id = phone
    page.goto(f"/admin/activiteiten/{activity_id}")
    pagina_klaar(page)
    # #1387: the header's button row is wider than a phone on master already
    # (685 px at 390). The link sits under the date line and must add nothing.
    row = page.evaluate(
        """() => { const r = document.querySelector('h1').closest('.justify-between');
                   return Math.round(r.scrollWidth); }"""
    )
    link = page.get_by_role("link", name="Kopiëren naar een volgend jaar")
    box = link.bounding_box()
    with_link = page.evaluate(WIDTH)[0]
    without_link = page.evaluate(
        """() => { const a = [...document.querySelectorAll('a')]
                     .find(e => e.textContent.trim() === 'Kopiëren naar een volgend jaar');
                   const p = a.parentElement, keep = p.style.display;
                   p.style.display = 'none';
                   const w = document.documentElement.scrollWidth;
                   p.style.display = keep;
                   return w; }"""
    )
    print("MEASURE header row", row, "page with/without link", with_link, without_link, box)
    _shot(page, "recordkop")
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390, (
        f"the link is off screen: {box}"
    )
    assert with_link == without_link, "the link widens the page"

    link.click()
    page.wait_for_url(re.compile(rf".*/admin/activiteiten/{activity_id}/kopieren$"))
    pagina_klaar(page)
    field = page.locator("#start_date")
    proposed = field.input_value()
    page.get_by_role("button", name="Zelfde datum, een jaar later").click()
    same_date = field.input_value()
    width = page.evaluate(WIDTH)
    print("MEASURE step", {"proposed": proposed, "same_date": same_date, "width": width})
    _shot(page, "kopieerstap")
    assert proposed == "2027-12-24", "the proposal is the same weekday, 52 weeks later"
    assert same_date == "2027-12-25"
    assert width[0] <= width[1], f"the copy step is wider than the phone: {width}"

    page.get_by_role("button", name="Kopie maken").click()
    page.wait_for_url(re.compile(r".*/admin/activiteiten/(\d+)$"))
    new_id = int(page.url.rsplit("/", 1)[1])
    print("MEASURE copy", new_id)
    assert new_id != activity_id


def test_the_copy_on_the_public_agenda_has_no_registration(phone):
    b, page, activity_id = phone
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import copy_activity

    db = SessionLocal()
    try:
        copy = copy_activity(db, activity_id, first_date=date(2027, 12, 25))
        # The public address is the slug when there is one, else the id (#884).
        copy_id, key = copy.id, copy.slug or str(copy.id)
    finally:
        db.close()

    visitor = b.new_page(base_url=BASE, viewport=PHONE)
    try:
        visitor.goto("/activiteiten")
        pagina_klaar(visitor)
        card = visitor.locator(f'a[href="/activiteiten/{key}"]').first
        assert card.count() == 1, "the copy is on the public agenda"
        on_agenda = visitor.evaluate(
            f"""() => ({{register: document.querySelectorAll('a[href^="/activiteiten/{copy_id}/inschrijven"]').length,
                        width: [document.documentElement.scrollWidth, innerWidth]}})"""
        )
        visitor.goto(f"/activiteiten/{key}")
        pagina_klaar(visitor)
        page_text = visitor.locator("main").inner_text()
        on_page = visitor.evaluate(
            f"""() => ({{register: document.querySelectorAll('a[href^="/activiteiten/{copy_id}/inschrijven"]').length,
                        width: [document.documentElement.scrollWidth, innerWidth]}})"""
        )
        _shot(visitor, "publiek-activiteit")
        print("MEASURE public", on_agenda, on_page, "Wie doet er mee" in page_text)
        assert on_agenda["register"] == 0 and on_page["register"] == 0
        assert "Wie doet er mee" not in page_text
        assert on_page["width"][0] <= on_page["width"][1]
    finally:
        visitor.close()

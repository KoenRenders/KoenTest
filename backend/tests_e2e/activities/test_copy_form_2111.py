"""E2E: the copy step on the kit keeps its behaviour (#2111).

"Activiteit kopiëren" moved onto the kit's form page: its two suggestions are the kit's
radio group, its status a second one, "Ook onderdelen en producten kopiëren" the kit's
switch. What the page did before is walked in the browser, at 390 px:

- the first suggestion is ticked and has filled the date;
- the second suggestion fills the date with its own, and is ticked instead;
- typing a date of one's own unticks both;
- the switch posts `with_components`: ticked it copies the components, and the
  save opens the copy.

Broken on purpose (18 October 2026): the wrapper's `@change` removed → the second
suggestion left the date as it was.
"""

import os
import re
import secrets
import sys
from datetime import timedelta

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.kernel.clock import belgian_today  # noqa: E402
from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402


def _activity() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate, ActivityStatus

    db = SessionLocal()
    try:
        activity = Activity(
            name=f"Kopieerwandeling {secrets.token_hex(2)}", status=ActivityStatus.DRAFT
        )
        db.add(activity)
        db.flush()
        db.add(
            ActivityDate(activity_id=activity.id, start_date=belgian_today() + timedelta(days=30))
        )
        db.commit()
        return activity.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def phone():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity_id = _activity()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = b.new_page(base_url=BASE, viewport={"width": 390, "height": 900})
        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL))
        yield page, activity_id
        b.close()


def test_the_suggestions_fill_the_date_and_a_typed_date_unticks_them(phone):
    page, activity_id = phone
    page.goto(f"/admin/activiteiten/{activity_id}/kopieren")
    pagina_klaar(page)
    weekday = page.locator("input[name=voorstel][value=weekdag]")
    same_date = page.locator("input[name=voorstel][value=datum]")
    start = page.locator("#start_date")
    first = start.input_value()
    assert weekday.is_checked() and not same_date.is_checked() and first, first

    same_date.check(force=True)
    second = start.input_value()
    assert same_date.is_checked() and not weekday.is_checked()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", second), second
    assert second != first, "the second suggestion left the date as it was"

    start.fill("2030-01-15")
    assert not weekday.is_checked() and not same_date.is_checked()
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0


def test_the_switch_posts_and_the_save_opens_the_copy(phone):
    page, activity_id = phone
    page.goto(f"/admin/activiteiten/{activity_id}/kopieren")
    pagina_klaar(page)
    page.locator("label[for=with_components]").click()
    assert page.locator("#with_components").is_checked()
    with page.expect_response(
        lambda r: r.url.endswith(f"/{activity_id}/kopieren") and r.request.method == "POST"
    ) as sent:
        page.locator("[data-action-bar] button[data-form-save]").click()
    body = sent.value.request.post_data or ""
    assert "with_components=1" in body or "with_components=true" in body, body
    page.wait_for_url(re.compile(r"/admin/activiteiten/(\d+)$"), timeout=15000)
    assert not page.url.endswith(f"/{activity_id}"), "the copy was not opened"

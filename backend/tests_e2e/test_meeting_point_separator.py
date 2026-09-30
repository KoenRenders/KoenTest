"""E2E: after saving a note, the first point of a section still has no line above
it (#1372).

The separator between points sat on each point, decided by `loop_first`, which only
the document loop knows. A point swapped back on its own after saving a note did
not know it was first, and grew a line right under the section heading. The line
now lives on the section's list (`divide-y`), so the fragment cannot get it wrong.

Proven red against master `3f3740c3` (the same test on the unchanged code): after
saving the note, the first point's top border went from 0 to 1 px.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, htmx_stil, login_als_admin  # noqa: E402

PHONE = 390
SHOTS = "/scratch/shots_1372"

# The top border of every point of the "Varia" section, in order.
_LINES = """() => {
  const card = [...document.querySelectorAll('#vg-document h2')]
    .find(h => h.textContent.trim() === 'Varia').closest('div.rounded-2xl');
  return [...card.querySelectorAll('[id^="vg-punt-"]')].map(p => ({
    label: p.querySelector('span').textContent.trim(),
    line: parseFloat(getComputedStyle(p).borderTopWidth),
  }));
}"""


def _add_free_point(page, title: str) -> None:
    varia = page.locator("#vg-document div.rounded-2xl", has=page.locator("h2", has_text="Varia"))
    varia.get_by_role("button", name="Punt toevoegen").click()
    htmx_stil(page)
    field = page.get_by_placeholder("Typ een vrij punt")
    field.fill(title)
    with htmx_afgerond(page):
        field.press("Enter")
    htmx_stil(page)


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


def test_the_first_point_has_no_line_after_its_note_is_saved(browser):
    tag = secrets.token_hex(2)
    first, second = f"Eerste punt {tag}", f"Tweede punt {tag}"
    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": PHONE, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto("/admin/vergaderingen/nieuw")
        page.fill("#vg-datum", "2030-09-05")
        page.click("button[type=submit]")
        page.wait_for_selector("#vg-document", timeout=10_000)
        htmx_stil(page)
        _add_free_point(page, first)
        _add_free_point(page, second)

        before = page.evaluate(_LINES)
        print("MEASURE before", before)
        assert [p["line"] > 0 for p in before] == [False, True], before

        # Save a note on the first point: the editor posts on blur, and the point
        # alone is swapped back.
        point = page.locator('[id^="vg-punt-"]', has_text=first)
        point.locator("trix-editor").click()
        page.keyboard.type("Wie brengt de tent mee?")
        with htmx_afgerond(page):
            page.locator("#vg-document h2", has_text="Varia").click()
        htmx_stil(page)

        after = page.evaluate(_LINES)
        print("MEASURE after", after)
        assert [p["label"] for p in after] == [first, second], after
        assert [p["line"] > 0 for p in after] == [False, True], (
            f"after the swap the first point grew a line: {after}"
        )
        assert page.evaluate("document.documentElement.scrollWidth") <= PHONE

        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.evaluate(
                """() => { const h = [...document.querySelectorAll('#vg-document h2')]
                    .find(h => h.textContent.trim() === 'Varia');
                  window.scrollTo(0, h.getBoundingClientRect().top + scrollY - 110); }"""
            )
            page.wait_for_function(
                "() => document.getAnimations().every(a => a.playState !== 'running')"
            )
            page.screenshot(path=f"{SHOTS}/390-na-notitie.png")
    finally:
        page.close()

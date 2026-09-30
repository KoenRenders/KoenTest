"""E2E: change the title of a free agenda point in place, at 390 px (#1359).

A free point is added under "Varia", its pencil opens the title in place, a new
title is saved, and an empty one is refused with the reason in the point. The
title field and its buttons stay inside the card.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, htmx_stil, login_als_admin  # noqa: E402

PHONE = 390
SHOTS = "/scratch/shots_1359"

_MEASURE = """(title) => {
  const point = [...document.querySelectorAll('[id^="vg-punt-"]')]
    .find(p => p.querySelector('input[name=title]') && p.querySelector('input[name=title]').value === title);
  const card = point.closest('div.rounded-2xl').getBoundingClientRect();
  const widest = Math.max(...[...point.querySelector('input[name=title]').closest('form').querySelectorAll('*')]
    .map(e => e.getBoundingClientRect().right));
  const input = point.querySelector('input[name=title]').getBoundingClientRect();
  return {
    doc: document.documentElement.scrollWidth, vw: innerWidth,
    card_right: Math.round(card.right), widest: Math.round(widest),
    input_width: Math.round(input.width),
  };
}"""


def _shot(page, name: str) -> None:
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.wait_for_function(
            "() => document.getAnimations().every(a => a.playState !== 'running')"
        )
        page.screenshot(path=f"{SHOTS}/{name}.png")


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


def test_a_free_point_title_is_changed_in_place(browser):
    typo = f"Tentn opbouwen {secrets.token_hex(2)}"
    fixed = typo.replace("Tentn", "Tenten")
    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": PHONE, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto("/admin/vergaderingen/nieuw")
        page.fill("#vg-datum", "2030-03-07")
        page.click("button[type=submit]")
        page.wait_for_selector("#vg-document", timeout=10_000)
        htmx_stil(page)

        varia = page.locator(
            "#vg-document div.rounded-2xl", has=page.locator("h2", has_text="Varia")
        )
        varia.get_by_role("button", name="Punt toevoegen").click()
        htmx_stil(page)
        page.get_by_placeholder("Typ een vrij punt").fill(typo)
        with htmx_afgerond(page):
            page.get_by_placeholder("Typ een vrij punt").press("Enter")
        htmx_stil(page)

        point = page.locator('[id^="vg-punt-"]', has_text=typo)
        point.get_by_role("button", name="Titel van het punt wijzigen").click()
        field = point.locator("input[name=title]")
        expect(field).to_be_visible()

        m = page.evaluate(_MEASURE, typo)
        print("MEASURE edit", m)
        assert m["doc"] <= m["vw"] and m["widest"] <= m["card_right"], m
        assert m["input_width"] > 150, m
        field.scroll_into_view_if_needed()
        _shot(page, "390-titel-bewerken")

        field.fill("   ")
        with htmx_afgerond(page):
            point.get_by_role("button", name="Opslaan").click()
        refused = page.locator('[id^="vg-punt-"]', has_text="Een vrij punt heeft een titel nodig.")
        expect(refused).to_have_count(1)
        refused.scroll_into_view_if_needed()
        _shot(page, "390-lege-titel-geweigerd")

        refused.locator("input[name=title]").fill(fixed)
        with htmx_afgerond(page):
            refused.get_by_role("button", name="Opslaan").click()
        saved = page.locator('[id^="vg-punt-"]', has_text=fixed)
        expect(saved.locator("span.font-semibold")).to_have_text(fixed)
        expect(
            page.locator('[id^="vg-punt-"]', has_text="Een vrij punt heeft een titel nodig.")
        ).to_have_count(0)
        saved.scroll_into_view_if_needed()
        _shot(page, "390-titel-bewaard")
    finally:
        page.close()

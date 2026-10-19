"""E2E: the meeting as a document page on the kit (#2112; CR-11 phase 5, round 1).

Walked in the browser: the record head carries the status, the facts and "Verslag
versturen…" with the rest under Acties; a saved point sends the head back, so
"Opgeslagen om" follows what was just typed; the head's edit page changes the
location and the facts say so; at 390 and 1 100 px the page does not scroll
sideways. When `E2E_PRINT_DIR` is set a print of the page and of its edit page is
taken at both widths (looked at by whoever hands the work over).

Broken on purpose (19 October 2026, each put back): the out-of-band head taken out of
`_vg_punt_antwoord.html` → the "Opgeslagen om" test is red; `last_saved_at` made to
return `None` → the same test is red; `form="vg-form"` dropped from the action bar of
the edit page → the edit test is red.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, login_met_sessie, pagina_klaar  # noqa: E402

LOCATION = "Zaal De Kring"


@pytest.fixture(scope="module")
def world():
    try:
        from app.domains.auth.api import make_session_value
        from tests.conftest import SEEDED_ADMIN_EMAIL

        session = make_session_value(SEEDED_ADMIN_EMAIL)
    except Exception as exc:  # pragma: no cover - only in a bare environment
        pytest.skip(f"backend not importable for the session value: {exc}")
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield {"browser": browser, "session": session}
        browser.close()


def _page(world, width):
    page = world["browser"].new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, world["session"])
    return page


def _new_meeting(page, day):
    page.goto("/admin/vergaderingen/nieuw")
    pagina_klaar(page)
    page.fill("#vg-datum", day)
    page.fill("#vg-uur", "20:00")
    page.fill("#vg-locatie", LOCATION)
    page.get_by_role("button", name="Vergadering aanmaken").click()
    page.wait_for_selector("#vg-document", timeout=10_000)
    pagina_klaar(page)
    return page.url


def _fill_the_circle(page):
    """The first person that matches a search goes into the circle, through its screen."""
    page.goto("/admin/vergaderingen/kring")
    page.wait_for_selector("#vg-kring")
    with htmx_afgerond(page):
        page.fill("input[name=q]", "e")
    add = page.locator("#vg-kring form[hx-post='/admin/vergaderingen/kring'] button")
    if add.count():
        with htmx_afgerond(page):
            add.first.click()


def _print(page, name, width):
    folder = os.environ.get("E2E_PRINT_DIR")
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    height = page.evaluate("document.documentElement.scrollHeight")
    page.set_viewport_size({"width": width, "height": max(900, min(height, 3600))})
    page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    page.screenshot(path=os.path.join(folder, f"{name}-{width}.png"), caret="initial")


def test_the_head_the_save_fact_and_the_edit_page(world):
    page = _page(world, 1100)
    try:
        url = _new_meeting(page, "2031-03-04")
        head = page.locator("[data-record-head]")
        expect(head.locator("h1")).to_contain_text("2031")
        expect(head.locator("[data-badge]")).to_have_count(1)
        facts = head.locator("[data-facts]")
        expect(facts).to_contain_text("20:00")
        expect(facts).to_contain_text(LOCATION)
        expect(facts).not_to_contain_text("Opgeslagen")
        expect(head.get_by_role("link", name="Verslag versturen…")).to_be_visible()
        head.locator("[data-actions-trigger]").click()
        menu = head.locator("[data-actions-menu]")
        for label in ("Datum, uur en locatie", "Agenda versturen…", "Download PDF"):
            expect(menu.get_by_role("menuitem", name=label)).to_be_visible()
        page.keyboard.press("Escape")

        # A free point under Varia, so there is a point whatever the seed holds.
        varia = page.locator(
            "#vg-document [data-vg-section]", has=page.locator("h2", has_text="Varia")
        )
        with htmx_afgerond(page):
            varia.get_by_role("button", name="Punt toevoegen").click()
        page.get_by_placeholder("Typ een vrij punt").fill("Een vrij punt")
        with htmx_afgerond(page):
            page.get_by_role("button", name="Toevoegen", exact=True).first.click()
        expect(page.locator('[id^="vg-punt-"]', has_text="Een vrij punt")).to_have_count(1)

        # A note on a point: the point swaps itself, the head follows out of band.
        editor = page.locator('[id^="vg-punt-"]', has_text="Een vrij punt").locator(".ProseMirror")
        editor.click()
        editor.type("Genoteerd voor de test.", delay=80)
        with htmx_afgerond(page):
            page.locator("#vg-document h2").first.click()
        expect(page.locator("[data-record-head] [data-facts]")).to_contain_text("Opgeslagen om")
        # What the print should show: a circle with someone present, a second point.
        _fill_the_circle(page)
        page.goto(url)
        pagina_klaar(page)
        ticks = page.locator("#vg-document form[hx-post*='aanwezigheid'] button")
        if ticks.count():
            with htmx_afgerond(page):
                ticks.first.click()
            expect(page.locator("[data-record-head] [data-facts]")).to_contain_text("1 aanwezig")
        _print(page, "vergadering-lezen", 1100)
        _print(page, "vergadering-lezen", 390)
        page.set_viewport_size({"width": 1100, "height": 900})

        # The edit page: the location changes and the facts say so.
        page.goto(url + "/bewerken")
        pagina_klaar(page)
        page.fill("#vg-locatie", "Café De Hoek")
        _print(page, "vergadering-kop-bewerken", 1100)
        _print(page, "vergadering-kop-bewerken", 390)
        page.set_viewport_size({"width": 1100, "height": 900})
        page.get_by_role("button", name="Wijziging bewaren").click()
        page.wait_for_selector("#vg-document", timeout=10_000)
        expect(page.locator("[data-record-head] [data-facts]")).to_contain_text("Café De Hoek")
        expect(page.locator("[data-record-head] [data-facts]")).to_contain_text("Opgeslagen")
    finally:
        page.close()


@pytest.mark.parametrize("width", [390, 1100])
def test_the_document_page_does_not_scroll_sideways(world, width):
    page = _page(world, width)
    try:
        url = _new_meeting(page, "2031-04-08")
        scroll = page.evaluate("document.documentElement.scrollWidth")
        wide = page.evaluate(
            """(w) => [...document.querySelectorAll('#vg-document *')]
                .filter(e => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().right > w + 1)
                .slice(0, 8).map(e => e.tagName + '.' + String(e.className).slice(0, 50))""",
            width,
        )
        assert scroll == width, f"the page scrolls sideways: {scroll} > {width}; {wide}"
        page.goto(url + "/bewerken")
        pagina_klaar(page)
        assert page.evaluate("document.documentElement.scrollWidth") == width
    finally:
        page.close()

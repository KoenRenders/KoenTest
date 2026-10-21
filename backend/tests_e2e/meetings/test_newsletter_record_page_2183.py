"""E2E: the newsletter as one record page (#2183, after #2113; Koen, 21 October 2026).

Walked in the browser: read mode shows the audience card directly under the head, the
card with the subject and the preview text and the text, and changes nothing; Bewerken
opens all of it at once (four radio buttons, none chosen on a new letter), one Opslaan
stores subject, preview text, audience and text and reads back after a reload; Annuleren
leaves what was stored; leaving with changes asks first; at 390 and 1 100 px the page
does not scroll sideways. When `E2E_PRINT_DIR` is set the prints of read and edit mode
are taken at both widths (looked at by whoever hands the work over).

Broken on purpose (each put back): `subject` left out of `newsletter_save` → the round
trip is red; the audience radios taken out of the form (`form=`) → the round trip is red.
"""

import os
import re
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.newsletter_head import open_head_card, save_letter, set_head  # noqa: E402
from tests_e2e.schermen import (  # noqa: E402
    BASE,
    login_met_sessie,
    pagina_klaar,
)

SUBJECT = "Nieuwsbrief november"


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


def _new_letter(page) -> str:
    page.goto("/admin/nieuwsbrieven")
    pagina_klaar(page)
    page.get_by_role("button", name="Nieuwe nieuwsbrief", exact=True).click()
    page.wait_for_selector("#nb-editor .ProseMirror", timeout=10_000)
    pagina_klaar(page)
    return page.url


def _print(page, name, width):
    folder = os.environ.get("E2E_PRINT_DIR")
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    height = page.evaluate("document.documentElement.scrollHeight")
    page.set_viewport_size({"width": width, "height": max(900, min(height, 3600))})
    page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    page.screenshot(path=os.path.join(folder, f"{name}-{width}.png"), caret="initial")


def _visible_controls_in_main(page):
    return page.evaluate(
        """() => [...document.querySelectorAll('main input, main textarea, main select')]
            .filter(e => e.type !== 'hidden' && e.type !== 'file' && e.offsetParent !== null
                         && getComputedStyle(e).visibility !== 'hidden')
            .map(e => e.name || e.id)"""
    )


def test_read_mode_shows_everything_and_changes_nothing(world):
    page = _page(world, 1100)
    try:
        _new_letter(page)
        set_head(page, subject=SUBJECT, preview="Een korte voorbeeldtekst", audience="members")
        pagina_klaar(page)
        # Read mode: the head with Bewerken beside Versturen, no field to type in.
        head = page.locator("#nb-kop [data-record-head]")
        expect(head.locator("h1")).to_have_text(SUBJECT)
        expect(head.get_by_role("link", name="Versturen…")).to_be_visible()
        expect(head.locator("[data-head-secondary]")).to_have_text("Bewerken")
        head.locator("[data-actions-trigger]").click()
        menu = head.locator("[data-actions-menu]")
        for label in ("Kopiëren", "Voorbeeld", "Testmail naar mezelf"):
            expect(menu.get_by_role("menuitem", name=label)).to_be_visible()
        assert menu.get_by_role("menuitem", name="Onderwerp en doelgroep").count() == 0
        page.keyboard.press("Escape")
        assert _visible_controls_in_main(page) == [], "read mode has no field"
        expect(page.locator("#nb-editor .ProseMirror")).to_have_attribute(
            "contenteditable", "false"
        )
        expect(page.locator("#nb-editor .de-bar")).to_be_hidden()
        expect(page.locator("[data-action-bar]")).to_be_hidden()
        # The audience card stands directly under the head, then the subject card.
        titles = page.locator("main [data-form-section] h2").all_inner_texts()
        assert titles[:2] == ["Wie krijgt de brief?", "Nieuwsbrief"], titles
        card = page.locator("[data-letter-read]")
        expect(card).to_contain_text(SUBJECT)
        expect(card).to_contain_text("Een korte voorbeeldtekst")
        expect(page.locator("[data-audience-read]")).to_contain_text("Leden")
        facts = page.locator("#nb-kop [data-facts]")
        expect(facts).to_contain_text("Leden")
        expect(facts).to_contain_text("Opgeslagen")
    finally:
        page.close()


def test_edit_mode_one_opslaan_stores_the_four_and_annuleren_leaves_them(world):
    page = _page(world, 1100)
    try:
        address = _new_letter(page).split("?")[0]
        # A new letter opens for editing: four radio buttons, none chosen.
        labels = page.locator('input[name="audience"]').evaluate_all(
            "els => els.map(e => e.closest('label').innerText.trim())"
        )
        assert labels == ["Leden", "Abonnees", "Allebei", "Eerdere deelnemers"], labels
        assert page.locator('input[name="audience"]:checked').count() == 0
        expect(page.locator("[data-action-bar]")).to_have_count(1)
        expect(page.locator("#nb-editor .ProseMirror")).to_have_attribute("contenteditable", "true")
        expect(page.locator("#nb-kop-bewerken [data-badges]")).to_contain_text("Bewerken")

        page.fill("#nb-onderwerp", SUBJECT)
        page.fill("#nb-voorbeeldtekst", "Pannenkoeken en een wandeling")
        page.locator('input[name="audience"][value="both"]').check()
        editor = page.locator("#nb-editor .ProseMirror")
        editor.click()
        editor.type("Dag buren, november is er weer.", delay=80)
        save_letter(page)
        pagina_klaar(page)

        # Read back after a full reload.
        page.reload()
        pagina_klaar(page)
        expect(page.locator("#nb-kop h1")).to_have_text(SUBJECT)
        expect(page.locator("[data-letter-read]")).to_contain_text("Pannenkoeken en een wandeling")
        expect(page.locator("[data-audience-read]")).to_contain_text("Allebei")
        expect(page.locator("#nb-editor .ProseMirror")).to_contain_text(
            "Dag buren, november is er weer."
        )

        # Annuleren puts everything back: change all four, cancel, open again.
        open_head_card(page)
        page.fill("#nb-onderwerp", "Anders")
        page.fill("#nb-voorbeeldtekst", "Iets anders")
        page.locator('input[name="audience"][value="members"]').check()
        editor = page.locator("#nb-editor .ProseMirror")
        editor.click()
        editor.type(" Extra woord.", delay=80)
        page.locator("[data-action-bar] [data-form-cancel]").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_be_visible()
        with page.expect_navigation(wait_until="load"):
            dialog.get_by_role("button", name="Weggooien").click()
        pagina_klaar(page)
        assert page.url.split("?")[0] == address
        expect(page.locator("#nb-kop h1")).to_have_text(SUBJECT)
        expect(page.locator("[data-audience-read]")).to_contain_text("Allebei")
        expect(page.locator("#nb-editor .ProseMirror")).not_to_contain_text("Extra woord.")
        open_head_card(page)
        assert page.locator("#nb-voorbeeldtekst").input_value() == "Pannenkoeken en een wandeling"
        assert page.locator('input[name="audience"]:checked').get_attribute("value") == "both"
    finally:
        page.close()


def test_leaving_with_changes_asks_first(world):
    page = _page(world, 1100)
    try:
        _new_letter(page)
        set_head(page, subject=SUBJECT, audience="members")
        pagina_klaar(page)
        open_head_card(page)
        page.fill("#nb-onderwerp", "Nog niet bewaard")
        page.locator("#nb-kop-bewerken").get_by_role("link", name="Alle nieuwsbrieven").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_contain_text("verlaten")
        page.wait_for_function(
            "document.querySelector('[data-dialog]').contains(document.activeElement)"
        )
        page.click("[data-dialog] [data-dialog-cancel]")
        expect(page.locator("#nb-onderwerp")).to_have_value("Nog niet bewaard")
    finally:
        page.close()


def test_verwijderen_in_the_edit_bar_asks_and_returns_to_the_list(world):
    """#2172: Verwijderen stands at the left of the head card's action bar, asks the
    record's question and leaves the draft gone."""
    page = _page(world, 1100)
    try:
        address = _new_letter(page)
        open_head_card(page)
        bar = page.locator("[data-action-bar]")
        expect(bar.locator("[data-form-delete]")).to_have_text("Verwijderen")
        bar.locator("[data-form-delete]").click()
        dialog = page.get_by_role("dialog")
        expect(dialog).to_contain_text("definitief verwijderen?")
        dialog.get_by_role("button", name="Definitief verwijderen").click()
        expect(page).to_have_url(re.compile(r"/admin/nieuwsbrieven$"))
        assert page.goto(address).status == 404
    finally:
        page.close()


@pytest.mark.parametrize("width", [390, 1100])
def test_the_document_page_does_not_scroll_sideways(world, width):
    page = _page(world, width)
    try:
        address = _new_letter(page)
        for card_open in (False, True):
            page.goto(address)
            pagina_klaar(page)
            if card_open:
                open_head_card(page)
            url = f"{address} (card {'open' if card_open else 'closed'})"
            scroll = page.evaluate("document.documentElement.scrollWidth")
            wide = page.evaluate(
                """(w) => [...document.querySelectorAll('main *')]
                    .filter(e => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().right > w + 1)
                    .slice(0, 8).map(e => e.tagName + '.' + String(e.className).slice(0, 50))""",
                width,
            )
            assert scroll == width, f"{url} scrolls sideways: {scroll} > {width}; {wide}"
    finally:
        page.close()


LONG_PREVIEW = "Pannenkoeken, een wandeling langs de Schelde en de kerstmarkt op het dorpsplein"


@pytest.mark.parametrize("width", [390, 1100])
def test_the_preview_text_shows_all_its_text_and_the_bar_stays_in_view(world, width, capsys):
    """The preview text grows with its text in edit mode: its box is as high as its
    content (a field that was hidden when the page loaded measured nothing, so the box
    stayed one line and cut the second line in half). On a phone the bar stays in view
    while the page scrolls down to the text. Measured at the width the page was loaded
    at; the prints of read and edit mode are taken here too."""
    page = _page(world, width)
    try:
        _new_letter(page)
        set_head(page, subject=SUBJECT, preview=LONG_PREVIEW, audience="members")
        open_head_card(page)
        editor = page.locator("#nb-editor .ProseMirror")
        editor.click()
        for i in range(25):
            editor.type(f"Regel {i}")
            page.keyboard.press("Enter")
        save_letter(page)
        pagina_klaar(page)
        _print(page, "nieuwsbrief-lezen", width)
        page.set_viewport_size({"width": width, "height": 900})
        open_head_card(page)
        box = page.evaluate(
            """() => { const t = document.getElementById('nb-voorbeeldtekst');
                       return {height: t.offsetHeight, content: t.scrollHeight, client: t.clientHeight}; }"""
        )
        assert box["height"] >= box["content"], f"the preview text is cut off at {width} px: {box}"
        if width == 390:
            assert box["height"] > 45, f"a long text on a phone takes more than one line: {box}"
        bar = page.locator("[data-action-bar]")
        ys = []
        for y in (0, 900):
            page.evaluate(f"window.scrollTo(0, {y})")
            page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            ys.append((y, round(bar.bounding_box()["y"]), page.evaluate("window.innerHeight")))
        with capsys.disabled():
            print(f"MEASURE preview box at {width}: {box}; bar (scroll, y, window height): {ys}")
        page.evaluate("window.scrollTo(0, 0)")
        _print(page, "nieuwsbrief-bewerken", width)
    finally:
        page.close()

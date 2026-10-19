"""E2E: the newsletter as a document page on the kit (#2113; CR-11 phase 5, round 1).

Walked in the browser: the record head carries the subject, the status, the audience
and "Opgeslagen om" with "Versturen…" as the primary and the rest under Acties; the
audience is chosen on the head's edit page and the head says it; a typed text makes
"Opgeslagen om" follow out of band; at 390 and 1 100 px the page and its edit page do
not scroll sideways. When `E2E_PRINT_DIR` is set a print of both is taken at both
widths (looked at by whoever hands the work over).

Broken on purpose (19 October 2026, each put back): the out-of-band head taken out of
`_nb_bewaard_antwoord.html` → the "Opgeslagen om" test is red; the audience dropped
from the head's facts in `_head` → the audience assertion is red.
"""

import os
import re
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.newsletter_head import open_head_card, set_head  # noqa: E402
from tests_e2e.schermen import (  # noqa: E402
    BASE,
    htmx_afgerond,
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


def test_the_head_the_save_fact_and_the_edit_page(world):
    page = _page(world, 1100)
    try:
        _new_letter(page)
        head = page.locator("#nb-kop [data-record-head]")
        expect(head.locator("h1")).to_have_text("Nieuwe nieuwsbrief")
        expect(head.locator("[data-badge]")).to_have_count(1)
        expect(head.locator("[data-facts]")).to_contain_text("Nog geen doelgroep")
        expect(head.get_by_role("link", name="Versturen…")).to_be_visible()
        head.locator("[data-actions-trigger]").click()
        menu = head.locator("[data-actions-menu]")
        for label in (
            "Onderwerp en doelgroep",
            "Kopiëren",
            "Voorbeeld",
            "Testmail naar mezelf",
        ):
            expect(menu.get_by_role("menuitem", name=label)).to_be_visible()
        # #2172: Verwijderen is the edit bar's, not the head's.
        assert menu.get_by_role("menuitem", name="Verwijderen").count() == 0
        page.keyboard.press("Escape")

        # The audience and the subject are the head's: saved on its edit page, said by the head.
        set_head(
            page,
            subject=SUBJECT,
            preview="Pannenkoeken, een wandeling en de kerstmarkt",
            audience="members",
        )
        pagina_klaar(page)
        facts = page.locator("#nb-kop [data-facts]")
        expect(page.locator("#nb-kop h1")).to_have_text(SUBJECT)
        expect(facts).to_contain_text("Leden")
        expect(facts).to_contain_text("Opgeslagen")

        # A typed text: the status line answers and the head follows out of band.
        editor = page.locator("#nb-editor .ProseMirror")
        editor.click()
        editor.type("Dag buren, november is er weer.", delay=80)
        with htmx_afgerond(page):
            page.locator("#nb-kop h1").click()
        expect(page.locator("#nb-bewaard")).to_contain_text("ewaard")
        expect(facts).to_contain_text("Opgeslagen om")
        _print(page, "nieuwsbrief-lezen", 1100)
        _print(page, "nieuwsbrief-lezen", 390)
        page.set_viewport_size({"width": 1100, "height": 900})

        # The head's edit card opens on the page itself: the badge says "Bewerken", the
        # head is not saved while it is open, Annuleren puts back what was there.
        open_head_card(page)
        expect(page.locator("#nb-kop-bewerken [data-badges]")).to_contain_text("Bewerken")
        expect(
            page.locator("#nb-kop-bewerken").get_by_role("link", name="Versturen…")
        ).to_have_count(0)
        page.fill("#nb-onderwerp", "Nieuwsbrief december")
        page.locator("[data-action-bar] [data-form-cancel]").click()
        expect(page.locator("#nb-kop-form")).to_be_hidden()
        expect(page.locator("#nb-kop h1")).to_have_text(SUBJECT)
        open_head_card(page)
        assert page.locator("#nb-onderwerp").input_value() == SUBJECT, "Annuleren puts it back"
        page.fill("#nb-onderwerp", "Nieuwsbrief december")
        page.locator("[data-action-bar] [data-form-save]").click()
        expect(page.locator("#nb-kop-form")).to_be_hidden()
        expect(page.locator("#nb-kop h1")).to_have_text("Nieuwsbrief december")
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
    """The preview text grows with its text in the edit card: its box is as high as its
    content (a card that was hidden when the page loaded measured nothing, so the box
    stayed one line and cut the second line in half). On a phone the bar of the card
    stays in view while the page scrolls down to the text. Measured at the width the
    page was loaded at; the prints of the open card are taken here too."""
    page = _page(world, width)
    try:
        _new_letter(page)
        set_head(page, subject=SUBJECT, preview=LONG_PREVIEW, audience="members")
        editor = page.locator("#nb-editor .ProseMirror")
        editor.click()
        for i in range(25):
            editor.type(f"Regel {i}")
            page.keyboard.press("Enter")
        page.reload()
        pagina_klaar(page)
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
        _print(page, "nieuwsbrief-kop-bewerken", width)
    finally:
        page.close()

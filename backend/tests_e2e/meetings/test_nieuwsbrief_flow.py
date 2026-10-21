"""E2E for the newsletter (#984) and the confirmations that now appear (#939).

What only a browser can prove: that the editor's "Activiteit" block really lands
in the letter, that autosave really stores it, that the public signup
block works on a phone, and that a delete question really opens the dialog —
the server tests showed the attribute moved, not that htmx reads it there.

No data-dependent skips: a flow that skips itself when the data is not right
covers exactly nothing (#939).
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.newsletter_head import open_head_card, save_letter, set_head  # noqa: E402
from tests_e2e.schermen import (  # noqa: E402
    BASE,
    laat_de_wacht_passeren,
    login_als_admin,
    netwerk_bijgewerkt,
)

TELEFOON = {"width": 390, "height": 844}


def _admin_email() -> str:
    override = os.environ.get("E2E_ADMIN_EMAIL")
    if override:
        return override
    from tests.conftest import SEEDED_ADMIN_EMAIL

    return SEEDED_ADMIN_EMAIL


def _klikbaar(page, selector: str) -> None:
    """Wait until the element is really hit-testable.

    The shells use cross-document view transitions (`@view-transition`); while
    one runs, the whole page answers a hit test with the root element, so a click
    lands nowhere. 120 ms in a browser, noticeably longer headless — measured:
    `elementFromPoint` returned <html> right after the redirect and the input
    itself a moment later.
    """
    page.locator(selector).first.scroll_into_view_if_needed()
    page.wait_for_function(
        """sel => { const el = document.querySelector(sel); if (!el) return false;
                    const r = el.getBoundingClientRect();
                    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
                    return hit === el || el.contains(hit); }""",
        arg=selector,
        timeout=5_000,
    )


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        instance = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture
def admin_page(browser):
    from app.domains.auth.api import make_session_value

    email = _admin_email()
    page = browser.new_page(base_url=BASE)
    login_als_admin(page, email, make_session_value(email))
    page.goto("/admin/nieuwsbrieven")
    assert page.locator("#nb-lijst").count() == 1, page.content()[:300]
    yield page
    page.close()


def test_een_activiteit_invoegen_en_bewaren(admin_page):
    """New letter → subject and audience → insert an activity block through the
    editor's menu → autosave → after a reload the block is still there."""
    page = admin_page
    page.get_by_role("button", name="Nieuwe nieuwsbrief", exact=True).click()
    page.wait_for_selector("#nb-editor .ProseMirror", timeout=10_000)
    _klikbaar(page, "#nb-editor .ProseMirror")
    adres = set_head(page, subject="Het najaar in de e2e", audience="members")
    open_head_card(page)

    editor = page.locator("#nb-editor .ProseMirror")
    editor.click()
    page.keyboard.type("Beste,", delay=40)
    page.keyboard.press("Enter")

    page.locator("#nb-editor summary").click()
    # The letter set: a picture, a button and the three blocks of the letter.
    assert page.locator("#nb-editor .de-menu-item").all_inner_texts() == [
        "Afbeelding",
        "Knop",
        "Activiteit",
        "Kalender",
        "Afsluiting",
    ]
    page.locator("#nb-editor .de-menu-item", has_text="Activiteit").click()
    keuze = page.locator("[data-activity-pick] option").first
    assert keuze.count() == 1, "de seed hoort minstens één komende activiteit te leveren"
    naam = (keuze.text_content() or "").split(" · ")[0].strip()
    page.locator("[data-activity-apply]").click()
    page.wait_for_function(
        "naam => [...document.querySelectorAll('#nb-editor [data-letter-block=activity]')]"
        ".some(b => b.textContent.includes(naam))",
        arg=naam,
        timeout=5_000,
    )

    # A second and a third block stand AFTER the first: the selection after an inserted
    # block is the block itself, and an insert over it would have taken its place.
    for label in ("Kalender", "Afsluiting"):
        page.locator("#nb-editor summary").click()
        page.locator("#nb-editor .de-menu-item", has_text=label).click()
    soorten = page.evaluate(
        "[...document.querySelectorAll('#nb-editor [data-letter-block]')].map(b => b.dataset.letterBlock)"
    )
    assert soorten == ["activity", "calendar", "closing"], soorten

    # Nothing saves itself (#2183): Opslaan stores the text, and the page is read again.
    save_letter(page)

    page.goto(adres)
    page.wait_for_selector("#nb-editor .ProseMirror")
    _klikbaar(page, "#nb-editor .ProseMirror")
    bewaard = page.locator("#nb-editor-input").get_attribute("value") or ""
    # The letter holds the activity NUMBER as a block; the mail builds the block with
    # picture and registration link when it is sent (#984, #2023).
    assert '"type":"activity"' in bewaard.replace(" ", ""), "het blok van de activiteit ontbreekt"
    assert "<table" not in bewaard
    assert page.evaluate(
        "[...document.querySelectorAll('#nb-editor [data-letter-block]')].map(b => b.dataset.letterBlock)"
    ) == ["activity", "calendar", "closing"]
    assert "Leden" in page.locator("#nb-kop [data-facts]").inner_text()
    assert page.locator("#nb-kop h1").inner_text() == "Het najaar in de e2e"


def test_een_agendapunt_weghalen_vraagt_eerst_bevestiging(admin_page):
    """#939/#984: the question sat on the button and never appeared.

    Broken on purpose: `data-confirm` moved back from the form to the button in
    `_vg_punt.html` → no dialog opens, and this test fails — the same thing a
    board member saw before the fix.

    #997: the unchanged count is an absence, checked behind `netwerk_bijgewerkt`.
    Proved by making it happen: `cancel()` sending the request anyway → this test
    fails on the count (measured).
    """
    page = admin_page
    page.goto("/admin/vergaderingen/nieuw")
    page.fill("#vg-datum", "2026-10-02")
    page.click("button[type=submit]")
    page.wait_for_selector("#vg-document", timeout=10_000)
    _klikbaar(page, "button[aria-label='Punt van deze agenda halen']")

    weghalen = page.locator("button[aria-label='Punt van deze agenda halen']")
    assert weghalen.count() > 0, "een verse agenda hoort punten te hebben"
    aantal = weghalen.count()
    weghalen.first.click()

    dialoog = page.get_by_text("Dit punt van de agenda halen?")
    dialoog.wait_for(timeout=3_000)
    page.get_by_role("button", name="Annuleren").click()
    expect(dialoog).to_be_hidden()
    # #997: an absence check — only after the barrier, not after a fixed wait.
    netwerk_bijgewerkt(page)
    assert page.locator("button[aria-label='Punt van deze agenda halen']").count() == aantal


def test_inschrijven_via_de_link_op_de_homepagina_op_een_telefoon(browser):
    """Koen, 19 September 2026: the home page links to the newsletter, and the
    signup itself lives on that page — no form under every public page."""
    page = browser.new_page(base_url=BASE, viewport=TELEFOON)
    try:
        page.goto("/")
        assert page.locator("#nb-voet").count() == 0, "geen inschrijfblok in de voet"
        # #1588: the call stands in the footer of every page (it was a link at
        # the bottom of the home page).
        _klikbaar(page, "#nb-voet-link")
        page.locator("#nb-voet-link").click()
        page.wait_for_selector("#nb-publiek", timeout=5_000)
        _klikbaar(page, "#nb-email")
        page.fill("#nb-email", "e2e-nieuwsbrief@example.org")
        laat_de_wacht_passeren(page)  # the guard's two seconds (#2039)
        page.locator("#nb-publiek").get_by_role("button", name="Inschrijven").click()
        page.get_by_text("Kijk in je mailbox").wait_for(timeout=5_000)
        breedte = page.evaluate("document.documentElement.scrollWidth")
        assert breedte <= TELEFOON["width"], f"de pagina scrollt horizontaal ({breedte}px)"
    finally:
        page.close()


def test_een_voorstel_komt_op_de_cursor_of_over_de_selectie(admin_page):
    """The client glue of "Toepassen" (Koen, 17 September 2026): a piece goes
    where the cursor stands, a rewrite replaces the selection — as one transaction
    of the editor, so undo still works.

    The server side is tested with a scripted model; here the answer to
    Toepassen is simulated by placing the same block the route renders: since
    #1562 the kit's proposal block (`data-form-proposal`, `data-proposal-auto`),
    with the placement on the field `body`; since #2023 its value is the list of
    blocks the editor takes over, and the positions are the editor's own.
    """
    page = admin_page
    page.get_by_role("button", name="Nieuwe nieuwsbrief", exact=True).click()
    page.wait_for_selector("#nb-editor .ProseMirror", timeout=10_000)
    _klikbaar(page, "#nb-editor .ProseMirror")
    page.evaluate(
        """() => window.raakDocumentEditor('nb-editor').commands.setContent(
            {type: 'doc', content: [{type: 'paragraph', content: [{type: 'text', text: 'Een twee drie.'}]}]})"""
    )

    def pas_toe(tekst, plaats, bereik=None):
        page.evaluate(
            """([tekst, plaats, bereik]) => {
            const block = document.createElement('form');
            block.setAttribute('data-form-proposal', ''); block.setAttribute('data-proposal-auto', '');
            block.innerHTML = '<script type="application/json" data-proposal-fields></scr' + 'ipt><p data-proposal-result hidden></p>';
            const value = [{type: 'paragraph', content: [{type: 'text', text: tekst}]}];
            block.querySelector('[data-proposal-fields]').textContent = JSON.stringify(
              [{name: 'body', label: 'Inhoud', value: value, placement: plaats, range: bereik}]);
            document.body.appendChild(block);
            window.raakFormProposal.scan();
        }""",
            [tekst, plaats, bereik],
        )

    tekst = "() => window.raakDocumentEditor('nb-editor').state.doc.textBetween(0, window.raakDocumentEditor('nb-editor').state.doc.content.size, '|')"
    # "Een twee drie." — the word "twee" stands at positions 5 to 9.
    page.evaluate(
        "() => window.raakDocumentEditor('nb-editor').commands.setTextSelection({from: 5, to: 9})"
    )
    pas_toe("TWEE", "selection", [5, 9])
    assert page.evaluate(tekst).startswith("Een TWEE drie."), page.evaluate(tekst)

    page.evaluate("() => window.raakDocumentEditor('nb-editor').commands.setTextSelection(1)")
    pas_toe("Bovenaan.", "cursor")
    assert "Bovenaan." in page.evaluate(tekst) and "Een TWEE drie." in page.evaluate(tekst)

    page.evaluate("() => window.raakDocumentEditor('nb-editor').commands.undo()")
    assert "Bovenaan." not in page.evaluate(tekst), "ongedaan maken werkt niet"

    pas_toe("Een hele nieuwe brief.", "replace")
    assert page.evaluate(tekst).strip("|") == "Een hele nieuwe brief."
    assert page.locator('[data-field="body"][data-proposal-applied]').count() == 1


def test_the_audience_card_and_the_editor_have_the_full_width(admin_page):
    """Koen, 17 September 2026: the audience choice stood in the way next to
    Raakje. Since #1562 there is no column beside the editor — the conversation is in
    the Assistent's panel, the choices stand above — and the card takes the whole
    column. Since #2183 the audience is the first card of the letter's page, four radio
    buttons in edit mode, and it says who each audience is (#1834).

    What holds, on a desktop and at 390 px: the explanation is in the card, nothing
    of the card sticks out of it, and the page does not scroll sideways.
    """
    page = admin_page
    page.get_by_role("button", name="Nieuwe nieuwsbrief", exact=True).click()
    page.wait_for_selector("#nb-editor .ProseMirror", timeout=10_000)
    _klikbaar(page, "#nb-editor .ProseMirror")
    address = page.url.split("?")[0]

    letter_page = """() => {
        const r = e => e.getBoundingClientRect();
        const card = document.getElementById('nb-editor').closest('[data-form-section]');
        const keuzes = document.querySelector('#nb-keuzes > *');
        return {card: [r(card).left, r(card).width], keuzes: [r(keuzes).left, r(keuzes).width],
                kolom: !!document.getElementById('nb-raakje'), onder: r(card).top >= r(keuzes).bottom,
                audience: [...document.querySelectorAll('input[name=audience]')].filter(e => e.checkVisibility()).length,
                page: document.documentElement.scrollWidth, window: window.innerWidth};
    }"""
    edit_page = """() => {
        const r = e => e.getBoundingClientRect();
        const said = document.querySelector('[data-audience-said]');
        const card = said.closest('[data-form-section]'), box = r(card);
        const inside = [...card.querySelectorAll('*')].filter(e => e.checkVisibility());
        return {lines: card.querySelectorAll('[data-audience-line]').length, seen: inside.length,
                out: inside.filter(e => r(e).left < box.left - 0.5 || r(e).right > box.right + 0.5
                                     || r(e).bottom > box.bottom + 0.5).length,
                page: document.documentElement.scrollWidth, window: window.innerWidth};
    }"""
    for width in (None, 390):
        if width:
            page.set_viewport_size({"width": width, "height": 844})
        page.goto(address)
        page.wait_for_selector("#nb-editor .ProseMirror")
        maten = page.evaluate(letter_page)
        at = f"at {maten['window']} px"
        assert not maten["kolom"], "no column of Raakje beside the editor"
        assert maten["card"] == maten["keuzes"], f"the editor is as wide as the choices, {at}"
        assert maten["onder"], f"the choices stand above the editor, {at}"
        assert maten["audience"] == 0, f"the audience is not edited while the letter is read, {at}"
        assert maten["page"] <= maten["window"], f"the page scrolls sideways, {at}: {maten['page']}"

        open_head_card(page)
        maten = page.evaluate(edit_page)
        assert maten["lines"] >= 2, f"the card says who each audience is, {at}: {maten['lines']}"
        assert maten["seen"] > maten["lines"], "the card's content was not found — still looking?"
        assert maten["out"] == 0, f"{maten['out']} elements stick out of the card, {at}"
        assert maten["page"] <= maten["window"], f"the page scrolls sideways, {at}: {maten['page']}"

"""E2E for the newsletter (#984) and the confirmations that now appear (#939).

What only a browser can prove: that "Activiteit invoegen" really puts a line at
the cursor through Trix, that autosave really stores it, that the public signup
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

from tests_e2e.schermen import (BASE, htmx_afgerond, login_als_admin,  # noqa: E402
                                netwerk_bijgewerkt)

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
        arg=selector, timeout=5_000)


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
    """New letter → subject and audience → insert an activity at the cursor →
    autosave → after a reload the line is still there."""
    page = admin_page
    page.get_by_role("button", name="+ Nieuwe nieuwsbrief").click()
    page.wait_for_selector("#nb-trix", timeout=10_000)
    _klikbaar(page, "#nb-onderwerp")
    adres = page.url

    page.fill("#nb-onderwerp", "Het najaar in de e2e")
    page.locator("input[name=audience][value=members]").check()
    editor = page.locator("#nb-trix")
    editor.click()
    editor.type("Beste,")
    editor.press("Enter")

    page.get_by_role("button", name="Activiteit invoegen").click()
    page.wait_for_selector("#nb-kiezer-resultaten-insert", timeout=5_000)
    eerste = page.locator("#nb-kiezer-resultaten-insert button", has_text="Invoegen").first
    assert eerste.count() == 1, "de seed hoort minstens één komende activiteit te leveren"
    naam = page.locator("#nb-kiezer-resultaten-insert .font-medium").first.text_content().strip()
    eerste.click()
    page.wait_for_function(
        "naam => document.getElementById('nb-trix').editor.getDocument().toString().includes(naam)",
        arg=naam, timeout=5_000)

    # Autosave waits 1.5 s after the last change; leaving the editor saves at once
    # (`trix-blur`). #997: wait for that save to be answered, not for 2.5 s.
    with htmx_afgerond(page):
        page.locator("#nb-onderwerp").click()

    page.goto(adres)
    page.wait_for_selector("#nb-trix")
    _klikbaar(page, "#nb-onderwerp")
    bewaard = page.locator("#nb-inhoud").get_attribute("value") or ""
    assert naam in bewaard, "de ingevoegde verwijzing is niet bewaard"
    # #984, 19 September 2026: the letter holds the activity NUMBER; the block
    # with picture and registration link is built when it is sent. Measured:
    # Trix keeps no table and no class, and makes an inserted image its own
    # full-width attachment — which is what spilled out of a letter on HDEV.
    assert "[[activiteit:" in bewaard, "de markering naar de activiteit ontbreekt"
    assert "<table" not in bewaard and "trix-attachment" not in bewaard
    assert page.locator("input[name=audience][value=members]").is_checked()


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
        _klikbaar(page, "#nb-home-link")
        page.locator("#nb-home-link").click()
        page.wait_for_selector("#nb-publiek", timeout=5_000)
        _klikbaar(page, "#nb-email")
        page.fill("#nb-email", "e2e-nieuwsbrief@example.org")
        page.locator("#nb-publiek").get_by_role("button", name="Inschrijven").click()
        page.get_by_text("Kijk in je mailbox").wait_for(timeout=5_000)
        breedte = page.evaluate("document.documentElement.scrollWidth")
        assert breedte <= TELEFOON["width"], f"de pagina scrollt horizontaal ({breedte}px)"
    finally:
        page.close()


def test_een_voorstel_komt_op_de_cursor_of_over_de_selectie(admin_page):
    """The client glue of "Toepassen" (Koen, 17 September 2026): a piece goes
    where the cursor stands, a rewrite replaces the selection — through Trix,
    so undo still works.

    The server side is tested with a scripted model; here the panel's answer is
    simulated by placing the same <template> the route renders.
    """
    page = admin_page
    page.get_by_role("button", name="+ Nieuwe nieuwsbrief").click()
    page.wait_for_selector("#nb-trix", timeout=10_000)
    _klikbaar(page, "#nb-trix")
    page.evaluate("() => document.getElementById('nb-trix').editor.loadHTML('<div>Een twee drie.</div>')")

    def pas_toe(html, plaats, bereik=""):
        page.evaluate("""([html, plaats, bereik]) => {
            const t = document.createElement('template');
            t.id = 'nb-toepassen'; t.setAttribute('data-plaatsing', plaats);
            t.setAttribute('data-bereik', bereik); t.innerHTML = html;
            document.body.appendChild(t);
            document.body.dispatchEvent(new CustomEvent('htmx:afterSettle'));
        }""", [html, plaats, bereik])

    tekst = "() => document.getElementById('nb-trix').editor.getDocument().toString()"
    page.evaluate("() => document.getElementById('nb-trix').editor.setSelectedRange([4, 8])")
    pas_toe("<div>TWEE</div>", "selection", "4,8")
    assert page.evaluate(tekst).startswith("Een TWEE drie.")

    page.evaluate("() => document.getElementById('nb-trix').editor.setSelectedRange([0, 0])")
    pas_toe("<div>Bovenaan.</div>", "cursor")
    assert page.evaluate(tekst).startswith("Bovenaan.")
    assert "Een TWEE drie." in page.evaluate(tekst)

    page.evaluate("() => document.getElementById('nb-trix').editor.undo()")
    assert not page.evaluate(tekst).startswith("Bovenaan."), "ongedaan maken werkt niet"


def test_voor_wie_is_een_regel_hoog_en_lijnt_uit_met_de_rechterkolom(admin_page):
    """Koen, 17 September 2026: the audience choice stood in the way next to
    Raakje, and sat lower than the right column.

    Broken on purpose: the hidden CSRF field back as the form's first child →
    `space-y-4` pushes the card 16 px down and the alignment assertion fails.
    """
    page = admin_page
    page.get_by_role("button", name="+ Nieuwe nieuwsbrief").click()
    page.wait_for_selector("#nb-trix", timeout=10_000)
    _klikbaar(page, "#nb-onderwerp")

    maten = page.evaluate("""() => {
        const links = document.querySelector('#nb-formulier fieldset').getBoundingClientRect();
        const rechts = document.querySelector('#nb-formulier').parentElement.children[1]
                               .firstElementChild.getBoundingClientRect();
        return {links: links.top, rechts: rechts.top, hoogte: links.height};
    }""")
    assert abs(maten["links"] - maten["rechts"]) <= 1, maten
    assert maten["hoogte"] < 110, f"de keuze is {maten['hoogte']} px hoog"

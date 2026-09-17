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
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin  # noqa: E402

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

    # Autosave waits 1.5 s after the last change; leaving the editor saves at once.
    page.locator("#nb-onderwerp").click()
    page.wait_for_timeout(2_500)

    page.goto(adres)
    page.wait_for_selector("#nb-trix")
    _klikbaar(page, "#nb-onderwerp")
    bewaard = page.locator("#nb-inhoud").get_attribute("value") or ""
    assert naam in bewaard, "de ingevoegde regel is niet bewaard"
    assert "/activiteiten/" in bewaard, "de regel draagt geen inschrijflink"
    assert page.locator("input[name=audience][value=members]").is_checked()


def test_een_agendapunt_weghalen_vraagt_eerst_bevestiging(admin_page):
    """#939/#984: the question sat on the button and never appeared.

    Broken on purpose: `data-confirm` moved back from the form to the button in
    `_vg_punt.html` → no dialog opens, and this test fails — the same thing a
    board member saw before the fix.
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
    page.wait_for_timeout(500)
    assert page.locator("button[aria-label='Punt van deze agenda halen']").count() == aantal


def test_inschrijven_onderaan_de_site_op_een_telefoon(browser):
    page = browser.new_page(base_url=BASE, viewport=TELEFOON)
    try:
        page.goto("/")
        blok = page.locator("#nb-voet")
        blok.scroll_into_view_if_needed()
        _klikbaar(page, "#nb-voet-email")
        assert blok.count() == 1, "het inschrijfblok hoort onderaan elke afdelingssite"
        blok.scroll_into_view_if_needed()
        page.fill("#nb-voet-email", "e2e-nieuwsbrief@example.org")
        blok.get_by_role("button", name="Inschrijven").click()
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

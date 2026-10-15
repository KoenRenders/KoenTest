"""E2E: a section and a hero, built through the screens and measured in the
browser (CR-32 phase 1, C6 test 10; AC1 and AC2).

The walk: the author inserts a section around a paragraph, sets its tone and
eyebrow in the editor's bar, opens the page with a hero in the page's settings,
saves and publishes; the site shows both. The measurements are the ones the
change request promises, taken from the rendered DOM at 390 and 1 280 px: the
band spans the viewport edge to edge, the text inside it stands on the SAME
left line as the text above it (AC1), the hero's title is the page's one h1
(AC2), and the page never scrolls sideways.

Broken on purpose (15 October 2026): the padding that puts the container back
inside the band taken out of `.prose-section` → the text inside it moves to the
viewport's edge and the left-line measurement is red; `.prose-section` left out
of the 768 px `:not()` list → the band is 768 px wide, not the viewport's;
`overflow-x:clip` taken off the site body → the document scrolls sideways.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

EDITOR = "#cp-document"
_MENU = f"{EDITOR} details.de-menu-insert"


def _par(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


@pytest.fixture(scope="module")
def setup():
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import CmsPage, publish, save_document
    from app.domains.cms.service import create_page
    from app.schemas.cms import CmsPageCreate
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    walk = create_page(db, CmsPageCreate(title="Sectiewandeling", slug=f"sectie-{tag}"))
    save_document(db, walk.id, {"type": "doc", "content": [_par("Een alinea om te omringen.")]})
    publish(db, walk.id)
    walk_id, walk_slug = walk.id, walk.slug

    # The measured page, built as data: a paragraph, a tinted section, an accent
    # section with an eyebrow, a paragraph — and a hero as its opening.
    measured = create_page(db, CmsPageCreate(title="Gemeten pagina", slug=f"gemeten-{tag}"))
    save_document(
        db,
        measured.id,
        {
            "type": "doc",
            "content": [
                _par("De alinea boven de banden."),
                {
                    "type": "section",
                    "attrs": {"tone": "tint"},
                    "content": [_par("De tekst in de tint.")],
                },
                {
                    "type": "section",
                    "attrs": {"tone": "accent", "eyebrow": "De uitdaging"},
                    "content": [_par("De tekst in het accent.")],
                },
                _par("De alinea onder de banden."),
            ],
        },
    )
    publish(db, measured.id)
    measured.opening = "hero"
    measured.hero = {
        "tone": "tint",
        "eyebrow": "Over ons",
        "lead": "Wat wij doen, in een zin.",
        "buttons": [{"label": "Contact", "href": "https://example.test/contact"}],
    }
    plain = create_page(db, CmsPageCreate(title="Gewone pagina", slug=f"gewoon-{tag}"))
    save_document(db, plain.id, {"type": "doc", "content": [_par("Alleen tekst.")]})
    publish(db, plain.id)
    db.commit()
    ids = (walk_id, walk_slug, measured.slug, plain.slug, [walk.id, measured.id, plain.id])
    db.close()

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield (b, *ids[:4], make_session_value(SEEDED_ADMIN_EMAIL))
        b.close()
    cleanup = SessionLocal()
    try:
        cleanup.query(CmsPage).filter(CmsPage.id.in_(ids[4])).delete(synchronize_session=False)
        cleanup.commit()
    finally:
        cleanup.close()


def test_the_author_builds_a_section_and_a_hero_through_the_screens(setup):
    b, page_id, slug, _measured, _plain, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")

        page.click(f"{EDITOR} .tiptap p >> nth=0")
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Sectie").click()
        page.wait_for_selector(f"{EDITOR} .tiptap .prose-section")
        page.locator(f"{EDITOR} .de-section-tone").select_option("accent")
        page.locator(f"{EDITOR} .de-section-eyebrow").fill("De uitdaging")
        assert page.locator(f"{EDITOR} .tiptap .prose-section--accent").count() == 1
        assert (
            "Een alinea om te omringen."
            in page.locator(f"{EDITOR} .tiptap .prose-section").inner_text()
        ), "the section does not hold the paragraph she was made around"

        page.select_option("select[name=opening]", "hero")
        page.select_option("select[name=hero_tone]", "tint")
        page.fill("input[name=hero_eyebrow]", "Over ons")
        page.fill("textarea[name=hero_lead]", "Wat wij doen, in een zin.")
        page.fill("input[name=hero_b1_label]", "Contact")
        page.select_option("select[name=hero_b1_destination]", "href")
        page.fill("input[name=hero_b1_address]", "https://example.test/contact")

        page.locator("[data-action-bar] button[data-form-save]").click()
        page.wait_for_url(f"**/admin/paginas/{page_id}*opgeslagen=1*", timeout=15000)
        pagina_klaar(page)
        page.locator("button", has_text="Publiceren").click()
        page.wait_for_function(
            "() => document.querySelector('[data-record-head]') && "
            "!document.querySelector('[data-record-head]').textContent.includes('Concept gewijzigd')",
            timeout=15000,
        )

        page.goto(f"/{slug}")
        pagina_klaar(page)
        assert page.locator(".prose-hero.prose-hero--tint h1").count() == 1
        assert page.locator("main h1").count() == 1
        band = page.locator(".cms-page .prose-section.prose-section--accent")
        assert band.count() == 1, "the section did not reach the site"
        assert "de uitdaging" in band.inner_text().lower()
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


_MEASURE = """() => {
  const q = (s) => document.querySelector(s);
  const left = (el) => Math.round(el.getBoundingClientRect().left * 10) / 10;
  const box = (el) => { const r = el.getBoundingClientRect();
    return {left: Math.round(r.left * 10) / 10, width: Math.round(r.width * 10) / 10}; };
  const text = [...document.querySelectorAll('.cms-page p')];
  const find = (needle) => text.find(p => p.innerText.includes(needle));
  const tint = q('.prose-section--tint'), accent = q('.prose-section--accent');
  return {
    vw: innerWidth, scroll: document.documentElement.scrollWidth,
    above: left(find('boven de banden')), inTint: left(find('in de tint')),
    inAccent: left(find('in het accent')), below: left(find('onder de banden')),
    tint: box(tint), accent: box(accent), hero: box(q('.prose-hero')),
    heroTitle: left(q('.prose-hero h1')), heroLead: left(q('.prose-hero-lead')),
    heroH1: document.querySelectorAll('main h1').length,
    tintBg: getComputedStyle(tint).backgroundColor, accentBg: getComputedStyle(accent).backgroundColor,
    plainBg: getComputedStyle(q('.doc-page')).backgroundColor,
    eyebrow: q('.prose-section-eyebrow').innerText,
    // What is PAINTED, not what is measured: the element at both edges of a band
    // is the band's own (a holder with overflow clips it back to the container).
    paintLeft: (() => { const r = tint.getBoundingClientRect();
      const e = document.elementFromPoint(1, r.top + r.height / 2); return !!e && !!e.closest('.prose-section--tint'); })(),
    paintRight: (() => { const r = tint.getBoundingClientRect();
      const e = document.elementFromPoint(innerWidth - 2, r.top + r.height / 2); return !!e && !!e.closest('.prose-section--tint'); })(),
  };
}"""


@pytest.mark.parametrize("width", [1280, 390])
def test_the_bands_span_the_page_and_the_text_keeps_its_left_line(setup, width):
    b, _id, _slug, measured, _plain, _session = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    try:
        page.goto(f"/{measured}")
        pagina_klaar(page)
        m = page.evaluate(_MEASURE)
        print("MEASURE sections and hero", width, m)
        # Edge to edge, whatever the container leaves on each side.
        for name in ("tint", "accent", "hero"):
            assert m[name] == {"left": 0, "width": width}, (name, m[name])
        # One left line (AC1): the text in a band stands where the text above it stands.
        assert m["inTint"] == m["inAccent"] == m["above"] == m["below"], m
        assert m["heroTitle"] == m["heroLead"] == m["above"], "the hero is off the left line"
        assert m["heroH1"] == 1
        assert m["scroll"] == m["vw"], "the page scrolls sideways"
        assert m["tintBg"] != m["accentBg"] != m["plainBg"], (m["tintBg"], m["accentBg"])
        assert m["eyebrow"].lower() == "de uitdaging"
        assert m["paintLeft"] and m["paintRight"], "the band is clipped back to the container"
    finally:
        page.close()


def test_a_page_without_sections_and_hero_is_as_before(setup):
    b, _id, _slug, _measured, plain, _session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1280, "height": 900})
    try:
        page.goto(f"/{plain}")
        pagina_klaar(page)
        assert page.locator(".prose-hero, .prose-section").count() == 0
        assert page.locator("main h1").count() == 1
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
    finally:
        page.close()

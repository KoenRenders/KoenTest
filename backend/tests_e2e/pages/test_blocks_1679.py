"""E2E: the columns, the button and the callout (CR-17 phase 2, #1679,
slice 1's rest; C4.13) — pressed through the real editor and read on the
public page, because both halves are what the eye gets.

* the EDITOR half — the insert menu offers Kolommen, Knop and Kader in
  C4.13's order; the button's dialog carries her label, her variant and
  the ONE destination (Koen, 11 October 2026: a page, a form, Lid worden,
  an outside address — this walk picks Lid worden, the screen of this
  CR); the words typed in the columns and the callout survive the real
  save and the publish, read back on the public page;
* the LOOK half — C4.13's measures as computed styles: two equal columns
  32 px apart, the callout's radius and her surface, the kit's button —
  and on a phone the columns stack and the button takes her full width;
* the HOME INTRO half — the one living site block (Koen, 11 October 2026:
  the site blocks carry every block): a callout and a button in the
  intro's band stay inside her column and the page never scrolls
  sideways.

Proven red while building, each additive and restored: taking the
grid-template-columns rule off `.prose-columns` fell the look test on the
two equal columns; the `preview` flag taken off the unreachable button
left her words gone from the preview (the unit pin holds); and with the
button dialog's dispatch broken, this walk could not insert her.
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


def _blocks_document() -> dict:
    """The three blocks as a document — built as data, not parsed from old
    HTML: the parser walks what stored pages carry, and no stored page has
    ever carried these blocks (they are new in this slice)."""
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Een pagina met de nieuwe blokken erin."}],
            },
            {
                "type": "columns",
                "attrs": {"align": "top"},
                "content": [
                    {
                        "type": "column",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "De linker kolom van de meetpagina."}
                                ],
                            }
                        ],
                    },
                    {
                        "type": "column",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "De rechter kolom, even breed."}
                                ],
                            }
                        ],
                    },
                ],
            },
            {
                "type": "callout",
                "content": [{"type": "text", "text": "Een kader met alleen woorden."}],
            },
        ],
    }


@pytest.fixture(scope="module")
def setup():
    """One page carrying the three blocks as a published document, one
    browser — and the home intro's site block with a callout and a button
    in her document, the living site block of Koen's decision."""
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import CmsPage, create_page, publish, save_document
    from app.schemas.cms import CmsPageCreate
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    page = create_page(db, CmsPageCreate(title="Blokken", slug=f"blokken-{tag}"))
    doc = _blocks_document()
    # No button here: the screen walk below builds the one button this
    # page carries, and the look test reads her — a second fixture
    # button would break the locator and tell a different story.
    save_document(db, page.id, doc)
    publish(db, page.id)
    page_id, slug = page.id, page.slug
    # The intro of THIS page's tenant: every tenant carries her own
    # home-intro row (CR-19), and a bare query finds another tenant's —
    # the wrong intro (the lesson of the table fixture, commit 1).
    intro = (
        db.query(CmsPage)
        .filter(CmsPage.slug == "home-intro", CmsPage.tenant_id == page.tenant_id)
        .first()
    )
    intro_id = intro.id if intro is not None else None
    db.commit()
    db.close()

    if intro_id is not None:
        intro_doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "De intro met de nieuwe blokken."}],
                },
                {
                    "type": "callout",
                    "content": [{"type": "text", "text": "Een kader in de intro."}],
                },
                {
                    "type": "button",
                    "attrs": {"label": "Word lid", "variant": "primary", "screen": "lid-worden"},
                },
            ],
        }
        s = SessionLocal()
        save_document(s, intro_id, intro_doc)
        publish(s, intro_id)
        s.close()

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, page_id, slug, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def test_the_three_blocks_through_the_screen(setup):
    """The insert menu offers Kolommen, Knop and Kader; the button dialog
    carries her destination; the typed words survive the real save, the
    publish over a stored-HTML-less page (no confirmation), and the
    public page carries what the author built."""
    b, page_id, slug, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")

        # Kolommen: two columns, words typed in both.
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Kolommen").click()
        page.wait_for_selector(f"{EDITOR} .tiptap .prose-columns")
        page.click(f"{EDITOR} .tiptap .prose-column >> nth=0")
        page.keyboard.type("De eerste kolom.")
        page.click(f"{EDITOR} .tiptap .prose-column >> nth=1")
        page.keyboard.type("De tweede kolom.")

        # Kader: a box, words typed inside.
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Kader").click()
        page.wait_for_selector(f"{EDITOR} .tiptap .prose-callout")
        page.click(f"{EDITOR} .tiptap .prose-callout")
        page.keyboard.type("Een kader via het scherm.")

        # Knop: the dialog — label, variant, and Lid worden (the screen of
        # this CR; the tenant's pages and forms travel in the dialog too).
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Knop").click()
        # De vijf dialogen van het scherm dragen alle role="dialog"; de
        # knop heeft haar eigen staat als x-show — daarop gericht.
        page.wait_for_selector("div[x-show='button'][role='dialog']", state="visible")
        # A2 van de lezing van 12 oktober 2026: de paginalijst biedt de
        # siteblokken niet aan — de keuzes zijn wat de resolver oplost.
        page.locator("div[x-show='button'] button", has_text="Een pagina van de site").click()
        opties = page.locator("div[x-show='button'] select option").all_inner_texts()
        assert "Home intro" not in opties and "Site footer" not in opties, opties
        page.fill("#cp-document-btn-label", "Word lid via het scherm")
        page.locator("div[x-show='button'] button", has_text="Primair").click()
        page.locator("div[x-show='button'] button", has_text="Word lid").last.click()
        page.locator("div[x-show='button'] button", has_text="Invoegen").last.click()

        # Nog twee knoppen, NA ELKAAR op het bovenste niveau (S2 van de
        # lezing: twee knoppen na elkaar krijgen 8 px tussen haar en één
        # hoogte — de rand van de secundaire maakte haar 2 px groter dan
        # de primaire naast haar; gemeten door de looktest hieronder). Een
        # adres zonder http(s) wordt in de dialoog geweigerd, met een zin
        # aan het veld, en niets ingevoegd (S1). De pijl-rechts stapt van
        # de node-selectie af: na het invoegen staat de selectie OP de
        # knop, en "Knop" in het menu wijzigt dan de geselecteerde (A1)
        # i.p.v. een nieuwe te zetten.
        page.keyboard.press("ArrowRight")
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Knop").click()
        page.wait_for_selector("div[x-show='button'][role='dialog']", state="visible")
        page.fill("#cp-document-btn-label", "Naar buiten")
        page.locator("div[x-show='button'] button", has_text="Secundair").click()
        page.locator("div[x-show='button'] button", has_text="Een adres buiten de site").click()
        page.locator("div[x-show='button'] input[placeholder='https://']").fill(
            "www.voorbeeld.example"
        )
        page.locator("div[x-show='button'] button", has_text="Invoegen").last.click()
        page.wait_for_selector("div[x-show='button'] p[x-show='bFout']", state="visible")
        assert (
            "begint met http:// of https://"
            in page.locator("div[x-show='button'] p[x-show='bFout']").inner_text()
        )
        assert page.locator(f"{EDITOR} .tiptap a.prose-button").count() == 1
        page.locator("div[x-show='button'] input[placeholder='https://']").fill(
            "https://voorbeeld.test/buiten"
        )
        page.locator("div[x-show='button'] button", has_text="Invoegen").last.click()

        page.keyboard.press("ArrowRight")
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Knop").click()
        page.wait_for_selector("div[x-show='button'][role='dialog']", state="visible")
        page.fill("#cp-document-btn-label", "Ook buiten")
        page.locator("div[x-show='button'] button", has_text="Primair").click()
        page.locator("div[x-show='button'] button", has_text="Een adres buiten de site").click()
        page.locator("div[x-show='button'] input[placeholder='https://']").fill(
            "https://voorbeeld.test/nog"
        )
        page.locator("div[x-show='button'] button", has_text="Invoegen").last.click()

        # Opslaan door de balk van het recordformulier; dan publiceren.
        page.locator("[data-action-bar] button[data-form-save]").click()
        page.wait_for_url(f"**/admin/paginas/{page_id}*opgeslagen=1*", timeout=15000)
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")
        page.locator("button", has_text="Publiceren").click()
        page.wait_for_function(
            "() => document.querySelector('[data-record-head]') && "
            "!document.querySelector('[data-record-head]').textContent.includes('Concept gewijzigd')",
            timeout=15000,
        )

        # De publieke pagina draagt wat de auteur bouwde.
        page.goto(f"/{slug}")
        pagina_klaar(page)
        body = page.locator(".doc-page").inner_text()
        for woorden in ("De eerste kolom.", "De tweede kolom.", "Een kader via het scherm."):
            assert woorden in body, f"het scherm verloor {woorden!r}"
        assert page.locator(".doc-page a.prose-button").count() == 3
        knop = page.locator(".doc-page a.prose-button", has_text="Word lid via het scherm")
        assert knop.get_attribute("href") == "/lid-worden"
        buiten = page.locator(".doc-page a.prose-button", has_text="Naar buiten")
        assert buiten.get_attribute("href") == "https://voorbeeld.test/buiten"
        ook = page.locator(".doc-page a.prose-button", has_text="Ook buiten")
        assert ook.get_attribute("href") == "https://voorbeeld.test/nog"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_the_look_of_the_three_blocks(setup, width):
    """C4.13 as computed styles: two equal columns 32 px apart (stacked on
    a phone), the callout's radius and surface, the kit's button — full
    width on a phone; and the page never scrolls sideways."""
    b, _page_id, slug, _session = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        page.goto(f"/{slug}")
        pagina_klaar(page)
        look = page.evaluate(
            """() => { const kolommen = document.querySelector('.prose-columns');
              const c1 = kolommen.children[0].getBoundingClientRect();
              const c2 = kolommen.children[1].getBoundingClientRect();
              const kader = document.querySelector('.prose-callout');
              const ks = getComputedStyle(kader);
              const knoppen = document.querySelectorAll('.doc-page a.prose-button');
              const k1 = knoppen[knoppen.length - 2].getBoundingClientRect();
              const k2 = knoppen[knoppen.length - 1].getBoundingClientRect();
              const kolom = document.querySelector('.doc-page').getBoundingClientRect();
              return {kolommen: [Math.round(c1.width), Math.round(c2.width), Math.round(c2.x - (c1.x + c1.width))],
                      display: getComputedStyle(kolommen).display,
                      kader: [ks.borderTopLeftRadius, ks.backgroundColor, ks.padding],
                      knop: [Math.round(k1.width), Math.round(k1.height)],
                      knoppen: [Math.round(k1.height), Math.round(k2.height), Math.round(k2.x - (k1.x + k1.width)), Math.round(k2.width)],
                      kolom: [Math.round(kolom.width)],
                      page: [document.documentElement.scrollWidth, innerWidth]}; }"""
        )
        print("MEASURE blocks look", width, look)
        if width == 1440:
            assert look["display"] == "grid", look
            assert look["kolommen"][0] == look["kolommen"][1] == 496, look["kolommen"]
            assert look["kolommen"][2] == 32, f"de tussenruimte is geen 32 px: {look}"
            # S2 van de lezing van 12 oktober 2026: twee knoppen na elkaar
            # hebben 8 px tussen haar en één hoogte — de rand van de
            # secundaire maakte haar 2 px groter vóór de reparatie.
            assert look["knoppen"][0] == look["knoppen"][1], look["knoppen"]
            assert look["knoppen"][2] == 8, f"twee knoppen raken elkaar: {look['knoppen']}"
        if width == 390:
            assert look["display"] == "flex", look
            assert look["knop"][0] >= look["kolom"][0] - 1, (
                "de knop is op de telefoon niet volledige breedte"
            )
            assert look["knop"][1] >= 44, "de knop is op de telefoon geen 44 px hoog"
            assert look["knoppen"][3] >= look["kolom"][0] - 1, (
                "de tweede knop is op de telefoon niet volledige breedte"
            )
        assert look["kader"][0] == "14px", f"het kader heeft niet haar radius 14: {look['kader']}"
        assert look["page"] == [width, width], f"de pagina schuift zijwaarts: {look['page']}"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_the_blocks_in_the_home_intro_stay_in_her_band(setup, width):
    """Koen's decision of 11 October 2026: the site blocks carry every
    block — a callout and a button in the intro's band stay inside her
    column, and the page never scrolls sideways."""
    b, *_rest = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        page.goto("/")
        pagina_klaar(page)
        intro = page.evaluate(
            """() => { const h = document.querySelector('.home-intro');
              const r = h.getBoundingClientRect();
              const knop = h.querySelector('a.prose-button');
              const kb = knop ? knop.getBoundingClientRect() : null;
              return {breedte: [Math.round(r.x), Math.round(r.right)],
                      kader: h.querySelectorAll('.prose-callout').length,
                      knop: kb ? [Math.round(kb.x), Math.round(kb.right)] : null,
                      page: [document.documentElement.scrollWidth, innerWidth]}; }"""
        )
        print("MEASURE intro blocks", width, intro)
        assert intro["kader"] == 1, f"de intro draagt het kader niet: {intro}"
        assert intro["knop"] is not None and intro["knop"][1] <= intro["page"][1], (
            f"de knop van de intro loopt uit het venster: {intro}"
        )
        assert intro["breedte"][1] <= intro["page"][1], f"de intro breekt uit haar band: {intro}"
        assert intro["page"] == [width, width], f"de home schuift zijwaarts: {intro}"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def _knop_uit_document(document):
    """The first button's attrs, wherever she stands in the document."""
    for node in document.get("content") or []:
        if not isinstance(node, dict):
            continue
        if node.get("type") == "button":
            return node.get("attrs") or {}
        dieper = _knop_uit_document(node)
        if dieper:
            return dieper
    return {}


def _opgeslagen_knop(page_id):
    """What the save stored: the draft's button, from the database."""
    from app.database import SessionLocal
    from app.domains.cms.models import CmsPageTranslation

    s = SessionLocal()
    try:
        tr = s.query(CmsPageTranslation).filter(CmsPageTranslation.page_id == page_id).first()
        return _knop_uit_document(tr.draft_json or {})
    finally:
        s.close()


def test_a_buttons_destination_changes_and_exactly_one_survives(setup):
    """A1 of the review of 12 October 2026: changing an existing button's
    destination kept the old one standing — the save then refused the
    whole document with "precies één bestemming". Now all four travel
    with every change, the other three on null; the dialog opens on a
    CLICK on the button in the editor, filled with what she holds; and
    what is stored after each change is exactly one destination."""
    import time

    b, page_id, _slug, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")

        def bewaar(enkel, verwacht_sleutel, timeout=15):
            # De opslag herlaadt het record, en de url blijft tussen
            # opslagen dezelfde (opgeslagen=1) — een url-wacht keert dan
            # direct terug. De navigatie zelf wordt afgewacht: pas daarna
            # is de editor de nieuwe, en klikt de volgende stap niet op
            # een pagina die op het punt staat te verdwijnen.
            with page.expect_navigation(timeout=15000):
                page.locator("[data-action-bar] button[data-form-save]").click()
            pagina_klaar(page)
            page.wait_for_selector(f"{EDITOR} .tiptap")
            deadline = time.time() + timeout
            laatst = None
            while time.time() < deadline:
                laatst = _opgeslagen_knop(page_id)
                staat = {
                    k: v
                    for k, v in laatst.items()
                    if k in ("page_id", "form_slug", "screen", "href") and v is not None
                }
                # Het label hoort erbij: de schermknop van de screentest
                # hierboven staat óók in het document en draagt óók "screen"
                # — de poll meet de knop die deze test maakte.
                if (
                    laatst.get("label") == "Wissel mij"
                    and len(staat) == 1
                    and verwacht_sleutel in staat
                ):
                    return
                time.sleep(0.3)
            raise AssertionError(
                f"na de opslag draagt de knop niet precies één bestemming "
                f"({verwacht_sleutel}): {laatst}"
            )

        # Een knop, bestemming "Word lid" — de wissel begint bij haar.
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Knop").click()
        page.wait_for_selector("div[x-show='button'][role='dialog']", state="visible")
        page.fill("#cp-document-btn-label", "Wissel mij")
        page.locator("div[x-show='button'] button", has_text="Word lid").last.click()
        page.locator("div[x-show='button'] button", has_text="Invoegen").last.click()
        bewaar(None, "screen")

        # Elke wissel begint met een KLIK op de knop in de editor: de
        # dialoog opent gevuld met wat zij draagt, de andere drie
        # bestemmingen komen op null, en wat de opslag bewaart is precies
        # de ene nieuwe.
        for soort, knopje, vul in (
            ("page", "Een pagina van de site", None),
            ("form", "Een formulier", None),
            ("href", "Een adres buiten de site", "https://voorbeeld.test/wissel"),
            ("screen", "Word lid", None),
        ):
            page.click(f"{EDITOR} .tiptap a[data-button] >> nth=0")
            page.wait_for_selector("div[x-show='button'][role='dialog']", state="visible")
            assert page.locator("#cp-document-btn-label").input_value() == "Wissel mij", (
                "de dialoog opent niet met de woorden van de aangeklikte knop"
            )
            page.locator("div[x-show='button'] button", has_text=knopje).last.click()
            if vul:
                page.locator("div[x-show='button'] input[placeholder='https://']").fill(vul)
            page.locator("div[x-show='button'] button", has_text="Invoegen").last.click()
            bewaar(None, {"page": "page_id", "form": "form_slug"}.get(soort, soort))

        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()

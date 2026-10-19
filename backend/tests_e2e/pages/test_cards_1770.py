"""E2E: the cards block (CR-17 phase 2; C4.9, C4.13) — made through the real
editor, stored by the real save, and read on the public page.

* THE DIALOG — "Kaarten" in the insert menu opens the card's dialog; a card
  lands only with a title and a destination. A click on a card opens the
  dialog with what THAT card holds; a change of destination leaves exactly
  one destination in what is stored, walked through all four at 390 and at
  1 440 px; an address with a space is refused in a sentence at the field.
* THE CARDS MENU — shown while a card is selected: a card added after it,
  moved forward and back, removed; the last card takes its block along.
* THE LOOK — on the public page: three per row from the third card on, one
  card as wide as a card in a row of two, one per row on a phone; the whole
  card is the link and holds one link; the tile, the type sizes and the focus
  ring of C4.13.

Broken on purpose (13 October 2026), each put back by the reverse edit:
- a second destination left on the card at every change (one line added to the
  script's answer to the dialog) → the destination walk red at both widths:
  the save refuses the card and what is stored never changes;
- `:has(>:nth-child(3))` out of `.prose-cards` → the look test red at 1 440 px
  (the tops 256, 256, 436, 436: two in a row);
- `::after` off the title's link → the look test red at both widths ("a point
  on the card's line is not the link");
- the cards menu reading the live selection instead of the card it opened for
  → the menu test red at both widths: the menu hides under the pointer.
"""

import os
import secrets
import sys
import time

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (  # noqa: E402
    BASE,
    login_met_sessie,
    pagina_beeld_in_kiezer,
    pagina_klaar,
)

EDITOR = "#cp-document"
INSERT = f"{EDITOR} details.de-menu-insert"
CARDS_MENU = f"{EDITOR} details.de-menu-cards"
DIALOG = "div[x-show='card'][role='dialog']"
CARD = f"{EDITOR} .tiptap [data-card]"

#: How long a key is held, in milliseconds: as a person holds one. A press
#: without it is down and up at once, and then the keyup of the Escape that
#: closes a dialog reaches the dialog before the focus is back in the editor —
#: 569 of 600 such closings (13 October 2026). The 31 others, and every one of
#: 200 closings with the key held, had the keyup in the editor; that is where
#: an author's key always lands, and where the selected card was lost.
HELD = 80


def _paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _new_page(title: str, document: dict | None = None) -> tuple[int, str]:
    from app.database import SessionLocal
    from app.domains.cms.api import create_page, publish, save_document
    from app.schemas.cms import CmsPageCreate

    db = SessionLocal()
    try:
        # Out of the public menu: these pages are many, and a menu that grows
        # by nine items widens the header the other tests of the run measure.
        page = create_page(
            db,
            CmsPageCreate(title=title, slug=f"kaarten-{secrets.token_hex(3)}", show_in_nav=False),
        )
        save_document(db, page.id, document or {"type": "doc", "content": [_paragraph("Tekst.")]})
        publish(db, page.id)
        return page.id, page.slug
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _stored_cards(page_id: int) -> list[dict]:
    """The cards of the page's draft, as the save stored them."""
    from app.database import SessionLocal
    from app.domains.cms.models import CmsPageTranslation

    found: list[dict] = []

    def walk(node):
        if node.get("type") == "card":
            found.append(node.get("attrs") or {})
        for child in node.get("content") or []:
            walk(child)

    db = SessionLocal()
    try:
        row = db.query(CmsPageTranslation).filter(CmsPageTranslation.page_id == page_id).first()
        walk(row.draft_json or {})
        return found
    finally:
        db.close()


def _open(browser, session, page_id: int, width: int):
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    login_met_sessie(page, session)
    page.goto(f"/admin/paginas/{page_id}")
    pagina_klaar(page)
    page.wait_for_selector(f"{EDITOR} .tiptap")
    return page


def _save(page, page_id: int, expected) -> list[dict]:
    """Save the record and wait until what is stored answers `expected`."""
    with page.expect_navigation(timeout=15000):
        page.locator("[data-action-bar] button[data-form-save]").click()
    pagina_klaar(page)
    page.wait_for_selector(f"{EDITOR} .tiptap")
    deadline = time.time() + 15
    stored: list[dict] = []
    while time.time() < deadline:
        stored = _stored_cards(page_id)
        if expected(stored):
            return stored
        time.sleep(0.3)
    raise AssertionError(f"na de opslag draagt de kaart niet wat verwacht werd: {stored}")


def _destinations(card: dict) -> dict:
    return {
        k: v
        for k, v in card.items()
        if k in ("page_id", "href", "form_slug", "screen") and v is not None
    }


def _choose(page, text: str) -> None:
    page.locator(f"{DIALOG} button", has_text=text).last.click()


def _apply(page) -> None:
    page.locator(f"{DIALOG} [data-card-apply]").click()
    expect(page.locator(DIALOG)).to_be_hidden()


@pytest.mark.parametrize("width", [390, 1440])
def test_a_card_through_the_dialog_and_its_four_destinations(setup, width):
    browser, session = setup
    page_id, _slug = _new_page(f"Kaart door de dialoog {width}")
    page = _open(browser, session, page_id, width)
    try:
        # The insert menu offers one item for cards, and no "Linkkaart".
        page.locator(f"{INSERT} summary").click()
        items = [t.strip() for t in page.locator(f"{INSERT} button").all_inner_texts()]
        assert items.count("Kaarten") == 1 and "Linkkaart" not in items, items
        page.locator(f"{INSERT} button", has_text="Kaarten").click()
        expect(page.locator(DIALOG)).to_be_visible()

        # Nothing lands without a title.
        apply = page.locator(f"{DIALOG} [data-card-apply]")
        expect(apply).to_be_disabled()
        page.fill("#cp-document-card-title", "Zaalverhuur")
        page.fill("#cp-document-card-line", "Huur de zaal voor je feest")
        page.locator(f"{DIALOG} [data-card-top='icon']").click()
        # An icon was asked for and none is chosen yet: still not to insert.
        expect(apply).to_be_disabled()
        page.locator(f"{DIALOG} [data-card-icon='users']").click()
        page.fill("#cp-document-card-labels", "Gratis, Elke week")
        _choose(page, "Word lid")
        _apply(page)

        # The editor draws the card as the site will: icon, title, line, labels.
        card = page.locator(CARD)
        expect(card).to_have_count(1)
        assert card.locator(".prose-card-title").inner_text() == "Zaalverhuur"
        assert card.locator(".prose-card-icon svg").count() == 1, "the editor's card has no icon"
        assert card.locator(".prose-card-labels").inner_text() == "Gratis · Elke week"

        stored = _save(
            page, page_id, lambda cards: len(cards) == 1 and "screen" in _destinations(cards[0])
        )
        assert stored[0]["title"] == "Zaalverhuur" and stored[0]["icon"] == "users"
        assert stored[0]["line"] == "Huur de zaal voor je feest"
        assert stored[0]["labels"] == ["Gratis", "Elke week"] and stored[0].get("media_id") is None
        assert _destinations(stored[0]) == {"screen": "lid-worden"}

        # Each change starts with a click on the card: the dialog opens with
        # what that card holds, and what is stored is the one new destination.
        for label, key, address in (
            ("Een pagina van de site", "page_id", None),
            ("Een formulier", "form_slug", None),
            ("Een adres buiten de site", "href", "https://voorbeeld.test/zaal"),
            ("Word lid", "screen", None),
        ):
            page.locator(CARD).first.click()
            expect(page.locator(DIALOG)).to_be_visible()
            assert page.locator("#cp-document-card-title").input_value() == "Zaalverhuur", (
                "the dialog does not open with the words of the card clicked"
            )
            assert page.locator("#cp-document-card-labels").input_value() == "Gratis, Elke week"
            _choose(page, label)
            if address:
                field = page.locator(f"{DIALOG} input[placeholder='https://']")
                # An address with a space is refused at the field; the dialog stays.
                field.fill("https://voorbeeld.test/een zaal")
                page.locator(f"{DIALOG} [data-card-apply]").click()
                expect(page.locator(f"{DIALOG} p.text-red-700")).to_have_text(
                    "Een adres bevat geen spaties."
                )
                expect(page.locator(DIALOG)).to_be_visible()
                field.fill(address)
            _apply(page)
            expect(page.locator(CARD)).to_have_count(1)
            stored = _save(
                page,
                page_id,
                lambda cards, key=key: len(cards) == 1 and list(_destinations(cards[0])) == [key],
            )
            assert stored[0]["title"] == "Zaalverhuur" and stored[0]["icon"] == "users"

        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def test_a_picture_takes_the_icon_s_place(setup):
    """An icon or a picture, never both: choosing a picture for a card with an
    icon stores the picture and clears the icon."""
    browser, session = setup
    page_id, _slug = _new_page("Kaart met foto")
    page = _open(browser, session, page_id, 1440)
    try:
        page.locator(f"{INSERT} summary").click()
        page.locator(f"{INSERT} button", has_text="Kaarten").click()
        expect(page.locator(DIALOG)).to_be_visible()
        page.fill("#cp-document-card-title", "Met een foto")
        page.locator(f"{DIALOG} [data-card-top='icon']").click()
        page.locator(f"{DIALOG} [data-card-icon='image']").click()
        _choose(page, "Word lid")
        _apply(page)
        _save(page, page_id, lambda cards: len(cards) == 1 and cards[0].get("icon") == "image")

        page.locator(CARD).first.click()
        expect(page.locator(DIALOG)).to_be_visible()
        page.locator(f"{DIALOG} [data-card-top='picture']").click()
        picture = pagina_beeld_in_kiezer(page.locator(DIALOG))
        assert picture.count() == 1, "the seeded picture is not in the card's picker"
        picture.click()
        _apply(page)
        assert page.locator(f"{CARD} img.prose-card-picture").count() == 1
        stored = _save(page, page_id, lambda cards: len(cards) == 1 and cards[0].get("media_id"))
        assert stored[0].get("icon") is None, f"the icon stayed beside the picture: {stored[0]}"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def _titles(page) -> list[str]:
    return [t.strip() for t in page.locator(f"{CARD} .prose-card-title").all_inner_texts()]


def _menu(page, action: str):
    page.locator(f"{CARDS_MENU} summary").click()
    return page.locator(f"{CARDS_MENU} [data-card-action='{action}']")


@pytest.mark.parametrize("width", [390, 1440])
def test_the_cards_menu_adds_moves_and_removes(setup, width):
    browser, session = setup
    document = {
        "type": "doc",
        "content": [
            _paragraph("Boven de kaarten."),
            {
                "type": "cards",
                "content": [
                    {
                        "type": "card",
                        "attrs": {"title": "Eerste", "href": "https://voorbeeld.test/1"},
                    },
                    {
                        "type": "card",
                        "attrs": {"title": "Tweede", "href": "https://voorbeeld.test/2"},
                    },
                ],
            },
        ],
    }
    page_id, _slug = _new_page(f"Kaartenmenu {width}", document)
    page = _open(browser, session, page_id, width)
    try:
        # Hidden until a card is selected.
        expect(page.locator(CARDS_MENU)).to_be_hidden()
        page.locator(CARD).first.click()
        expect(page.locator(DIALOG)).to_be_visible()
        page.locator(f"{DIALOG} button", has_text="Annuleren").click()
        expect(page.locator(DIALOG)).to_be_hidden()
        expect(page.locator(CARDS_MENU)).to_be_visible()

        # The first card cannot go forward.
        expect(_menu(page, "forward")).to_be_disabled()
        expect(page.locator(f"{CARDS_MENU} [data-card-action='back']")).to_be_enabled()
        # A card added after the first one.
        page.locator(f"{CARDS_MENU} [data-card-action='add']").click()
        expect(page.locator(DIALOG)).to_be_visible()
        assert page.locator("#cp-document-card-title").input_value() == "", (
            "the dialog for a new card opens with another card's words"
        )
        page.fill("#cp-document-card-title", "Nieuw")
        _choose(page, "Een adres buiten de site")
        page.locator(f"{DIALOG} input[placeholder='https://']").fill("https://voorbeeld.test/n")
        _apply(page)
        assert _titles(page) == ["Eerste", "Nieuw", "Tweede"]

        # The new card is the selected one: one place back, then forward twice.
        _menu(page, "back").click()
        assert _titles(page) == ["Eerste", "Tweede", "Nieuw"]
        expect(_menu(page, "back")).to_be_disabled()
        page.locator(f"{CARDS_MENU} [data-card-action='forward']").click()
        _menu(page, "forward").click()
        assert _titles(page) == ["Nieuw", "Eerste", "Tweede"]

        stored = _save(page, page_id, lambda cards: len(cards) == 3)
        assert [c["title"] for c in stored] == ["Nieuw", "Eerste", "Tweede"]

        # Removed one by one; the last card takes its block along.
        for left in (2, 1, 0):
            page.locator(CARD).first.click()
            expect(page.locator(DIALOG)).to_be_visible()
            page.locator(f"{DIALOG} button", has_text="Annuleren").click()
            _menu(page, "remove").click()
            expect(page.locator(CARD)).to_have_count(left)
        expect(page.locator(f"{EDITOR} .tiptap [data-cards]")).to_have_count(0)
        expect(page.locator(CARDS_MENU)).to_be_hidden()
        _save(page, page_id, lambda cards: cards == [])
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def test_enter_on_a_selected_card_opens_its_dialog(setup):
    """The keyboard's way in to a card that is selected: Enter opens its
    dialog. The card is selected here by closing its dialog, which hands the
    focus back to the editor with the card still selected. (How the arrow keys
    reach a card is the editor's own; an arrow pressed right after a click was
    not steady enough to build a test on — two red runs in eight.)"""
    browser, session = setup
    document = {
        "type": "doc",
        "content": [
            _paragraph("Boven."),
            {
                "type": "cards",
                "content": [
                    {
                        "type": "card",
                        "attrs": {"title": "Met toetsen", "href": "https://voorbeeld.test/t"},
                    }
                ],
            },
        ],
    }
    page_id, _slug = _new_page("Kaart met toetsen", document)
    page = _open(browser, session, page_id, 1440)
    try:
        page.locator(CARD).first.click()
        expect(page.locator(DIALOG)).to_be_visible()
        page.locator(f"{DIALOG} button", has_text="Annuleren").click()
        expect(page.locator(DIALOG)).to_be_hidden()
        expect(page.locator(f"{EDITOR} .tiptap")).to_be_focused()
        expect(page.locator(CARDS_MENU)).to_be_visible()
        page.keyboard.press("Enter", delay=HELD)
        expect(page.locator(DIALOG)).to_be_visible()
        assert page.locator("#cp-document-card-title").input_value() == "Met toetsen"
        expect(page.locator(CARD)).to_have_count(1)
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


_SETTLE = """() => {
  if (window.__settle) return;
  window.__changes = 0;
  document.addEventListener('selectionchange', () => { window.__changes++; });
  // Resolves once the browser's selection has not changed for eight frames in a row.
  window.__settle = () => new Promise(resolve => {
    let seen = window.__changes, calm = 0;
    const frame = () => {
      if (window.__changes === seen) calm++; else { calm = 0; seen = window.__changes; }
      if (calm >= 8) resolve(true); else requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  });
}"""

_SELECTED = """() => {
  const card = document.querySelector('#cp-document .tiptap [data-card].ProseMirror-selectednode');
  return {card: card ? card.querySelector('.prose-card-title').textContent : null,
          menu: !document.querySelector('#cp-document details.de-menu-cards').hidden};
}"""


def _close_without_a_choice(page, way: str) -> None:
    if way == "Annuleren":
        page.locator(f"{DIALOG} button", has_text="Annuleren").click()
    elif way == "the close button":
        page.locator(f"{DIALOG} button[aria-label]").first.click()
    elif way == "a click outside":
        # The dialog stands centred on a backdrop that fills the window; its
        # corner is outside the dialog at every width.
        page.mouse.click(5, 5)
    else:
        page.keyboard.press("Escape", delay=HELD)
    expect(page.locator(DIALOG)).to_be_hidden()
    # The loss this test is about comes a few milliseconds AFTER the dialog is
    # gone: the focus returns to the editor first, the selection moves after.
    # A look taken at once sees the card still selected, also where it is about
    # to be lost. So the look waits until the selection has stopped changing —
    # counted in the browser's own frames, not on a clock.
    page.evaluate("() => window.__settle()")


@pytest.mark.parametrize("width", [390, 1440])
def test_a_card_stays_selected_when_its_dialog_closes_without_a_choice(setup, width):
    """A click on a card selects it and opens its dialog; Annuleren, the close
    button, a click outside the dialog and Escape close it and leave that card
    selected, with the cards menu there for it — for EVERY card of the block,
    not only the first and the last.

    Found on 13 October 2026, on the pushed cards commit: in a block of three
    or more cards, every card that is neither the first nor the last lost its
    selection when its dialog closed without a choice (54 of 54 such rounds
    over blocks of three, four and five cards; never the first or the last
    card, never after Invoegen). The browser's selection jumped to the start of
    the document some milliseconds after the focus returned to the editor, and
    the editor followed it. What moves the browser's selection there is NOT
    identified. The first version of this file never clicked an inner card and
    then cancelled, which is how it passed.

    A block of four: both inner cards and both outer ones, each closed in the
    four ways the kit's dialog has. Then the selection is put to use — Enter opens the dialog of
    the card that is selected, and a move from the menu moves that card — and
    what the form holds for the document is the same before and after all the
    closing, read from the form's own field.

    A limit, said plainly: "stays selected" is the absence of a change, and no
    finite look proves an absence. The look waits for eight frames without a
    change of selection; a loss that came later than that would pass here.

    Broken on purpose: see the commit that repairs it — on the commit before,
    this test is red at both widths at the first inner card.
    """
    browser, session = setup
    titles = ["K1", "K2", "K3", "K4"]
    document = {
        "type": "doc",
        "content": [
            _paragraph("Boven de kaarten."),
            {
                "type": "cards",
                "content": [
                    {"type": "card", "attrs": {"title": t, "href": f"https://voorbeeld.test/{t}"}}
                    for t in titles
                ],
            },
            _paragraph("Onder de kaarten."),
        ],
    }
    page_id, _slug = _new_page(f"Kaart blijft gekozen {width}", document)
    page = _open(browser, session, page_id, width)
    try:
        page.evaluate(_SETTLE)
        held_before = page.locator("#cp-document-input").input_value()
        lost = []
        for index, title in enumerate(titles):
            for way in ("Annuleren", "the close button", "a click outside", "Escape"):
                page.locator(CARD).nth(index).click()
                expect(page.locator(DIALOG)).to_be_visible()
                assert page.locator("#cp-document-card-title").input_value() == title, (
                    f"the dialog does not hold the card that was clicked ({title})"
                )
                _close_without_a_choice(page, way)
                seen = page.evaluate(_SELECTED)
                if seen != {"card": title, "menu": True}:
                    lost.append(
                        f"{title} closed with {way}: selected {seen['card']}, menu {seen['menu']}"
                    )
        assert not lost, f"at {width} px a card lost its selection or its menu: {lost}"

        # Nothing was chosen, so nothing may have changed in what a save would send.
        assert page.locator("#cp-document-input").input_value() == held_before, (
            "closing the dialogs without a choice changed the document the form holds"
        )

        # The selection put to use, on an inner card: Enter opens ITS dialog…
        page.locator(CARD).nth(2).click()
        expect(page.locator(DIALOG)).to_be_visible()
        _close_without_a_choice(page, "Escape")
        page.keyboard.press("Enter", delay=HELD)
        expect(page.locator(DIALOG)).to_be_visible()
        assert page.locator("#cp-document-card-title").input_value() == "K3"
        _close_without_a_choice(page, "Annuleren")
        # …and a move from the menu moves that card.
        _menu(page, "forward").click()
        assert _titles(page) == ["K1", "K3", "K2", "K4"]
        stored = _save(
            page, page_id, lambda cards: [c["title"] for c in cards] == ["K1", "K3", "K2", "K4"]
        )
        assert [c["href"] for c in stored] == [
            f"https://voorbeeld.test/{t}" for t in ("K1", "K3", "K2", "K4")
        ]
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


@pytest.mark.parametrize("way", ["Annuleren", "the close button", "a click outside", "Escape"])
def test_the_key_after_a_closed_dialog_goes_to_the_card_not_to_the_text_above(setup, way):
    """After the dialog of an inner card is closed without a choice, Delete
    removes THAT card — and the paragraph above the cards keeps every letter.

    Measured on the cards commit as first pushed (13 October 2026, one round
    per key): the selection had left the card for the start of the paragraph
    above, so Delete took that paragraph's first letter and left the card,
    Enter opened no dialog and put an empty paragraph above it, and a letter
    was typed into it — an edit of the page's text that the author did not
    make on purpose. This holds the consequence itself, beside the walk above
    that holds the selection.
    """
    browser, session = setup
    above = "Boven de kaarten staat deze zin."
    document = {
        "type": "doc",
        "content": [
            _paragraph(above),
            {
                "type": "cards",
                "content": [
                    {"type": "card", "attrs": {"title": t, "href": f"https://voorbeeld.test/{t}"}}
                    for t in ("K1", "K2", "K3", "K4")
                ],
            },
            _paragraph("Onder de kaarten."),
        ],
    }
    page_id, _slug = _new_page(f"Toets na sluiten {way[:6]}", document)
    page = _open(browser, session, page_id, 1440)
    try:
        page.evaluate(_SETTLE)
        page.locator(CARD).nth(1).click()
        expect(page.locator(DIALOG)).to_be_visible()
        _close_without_a_choice(page, way)
        page.keyboard.press("Delete", delay=HELD)
        expect(page.locator(CARD)).to_have_count(3)
        assert _titles(page) == ["K1", "K3", "K4"], (
            "Delete did not remove the card whose dialog was closed"
        )
        paragraphs = page.locator(f"{EDITOR} .tiptap > p").all_inner_texts()
        assert paragraphs[0] == above, (
            f"the key went into the text above the cards: {paragraphs[0]!r}"
        )
        stored = _save(
            page, page_id, lambda cards: [c["title"] for c in cards] == ["K1", "K3", "K4"]
        )
        assert len(stored) == 3
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


@pytest.mark.parametrize("index", [0, 1, 3])
def test_a_card_applied_as_it_was_stays_selected(setup, index):
    """A choice that changes nothing: the dialog of a card opened and applied
    without a change. The document is equal to the one the dialog opened on,
    so the place is put back as after Annuleren — and that is what an author
    expects there: that card still selected, the cards menu there for it,
    nothing different in what the form holds, and the next key for that card.
    The first card, an inner one and the last."""
    browser, session = setup
    titles = ["K1", "K2", "K3", "K4"]
    above = "Boven de kaarten staat deze zin."
    document = {
        "type": "doc",
        "content": [
            _paragraph(above),
            {
                "type": "cards",
                "content": [
                    {"type": "card", "attrs": {"title": t, "href": f"https://voorbeeld.test/{t}"}}
                    for t in titles
                ],
            },
            _paragraph("Onder de kaarten."),
        ],
    }
    page_id, _slug = _new_page(f"Kaart ongewijzigd {index}", document)
    page = _open(browser, session, page_id, 1440)
    try:
        page.evaluate(_SETTLE)
        held = page.locator("#cp-document-input").input_value()
        page.locator(CARD).nth(index).click()
        expect(page.locator(DIALOG)).to_be_visible()
        assert page.locator("#cp-document-card-title").input_value() == titles[index]
        _apply(page)
        page.evaluate("() => window.__settle()")
        assert page.evaluate(_SELECTED) == {"card": titles[index], "menu": True}
        assert page.locator("#cp-document-input").input_value() == held, (
            "a card applied as it was changed the document the form holds"
        )
        page.keyboard.press("Delete", delay=HELD)
        expect(page.locator(CARD)).to_have_count(3)
        assert _titles(page) == [t for t in titles if t != titles[index]]
        assert page.locator(f"{EDITOR} .tiptap > p").all_inner_texts()[0] == above
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


LOOK = """() => {
  const box = e => { const b = e.getBoundingClientRect(); return {left: b.left, right: b.right, top: b.top, width: b.width}; };
  const blocks = [...document.querySelectorAll('.prose-cards')].map(block => ({
    box: box(block),
    cards: [...block.querySelectorAll(':scope > .prose-card')].map(card => {
      const line = card.querySelector('.prose-card-line') || card.querySelector('.prose-card-title');
      const r = line.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + 4, r.top + r.height / 2);
      const tile = card.querySelector('.prose-card-icon');
      const css = (sel, prop) => { const e = card.querySelector(sel); return e ? getComputedStyle(e)[prop] : null; };
      return {box: box(card), links: card.querySelectorAll('a').length,
        a_point_on_the_line_is_the_link: !!(hit && hit.closest('a.prose-card-title')),
        tile: tile ? [tile.getBoundingClientRect().width, tile.getBoundingClientRect().height, getComputedStyle(tile).borderRadius] : null,
        title: css('.prose-card-title', 'fontSize'), line: css('.prose-card-line', 'fontSize'), labels: css('.prose-card-labels', 'fontSize'),
        radius: getComputedStyle(card).borderRadius};
    }),
  }));
  const wide = document.querySelector('.doc-page');
  return {blocks, container: wide ? box(wide) : null, window: [innerWidth, document.documentElement.scrollWidth]};
}"""


@pytest.mark.parametrize("width", [1440, 390])
def test_the_look_of_the_cards_on_the_public_page(setup, width):
    browser, _session = setup

    def card(title, **more):
        return {
            "type": "card",
            "attrs": {"title": title, "href": "https://voorbeeld.test/x", **more},
        }

    document = {
        "type": "doc",
        "content": [
            _paragraph("Drie kaarten en een vierde."),
            {
                "type": "cards",
                "content": [
                    card(
                        "Een",
                        icon="users",
                        line="Met een regel eronder",
                        labels=["Gratis", "Elke week"],
                    ),
                    card("Twee", line="Zonder icoon"),
                    card("Drie", icon="calendar-days"),
                    card("Vier"),
                ],
            },
            _paragraph("En een kaart alleen."),
            {"type": "cards", "content": [card("Alleen", line="Een losse linkkaart")]},
        ],
    }
    _page_id, slug = _new_page(f"Kaarten kijken {width}", document)
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        page.goto(f"/{slug}")
        pagina_klaar(page)
        seen = page.evaluate(LOOK)
        assert len(seen["blocks"]) == 2
        four, alone = seen["blocks"]
        assert [len(four["cards"]), len(alone["cards"])] == [4, 1]
        boxes = [c["box"] for c in four["cards"]]
        tops = [round(b["top"]) for b in boxes]
        if width == 1440:
            # The block fills the container, wider than the text's 768 px.
            assert four["box"]["width"] == pytest.approx(seen["container"]["width"], abs=1)
            assert four["box"]["width"] > 768
            # Three in the first row, the fourth alone at the left, not stretched.
            assert tops[0] == tops[1] == tops[2] and tops[3] > tops[0], tops
            assert boxes[3]["left"] == pytest.approx(boxes[0]["left"], abs=1)
            widths = [b["width"] for b in boxes]
            assert max(widths) - min(widths) < 1, widths
            assert boxes[1]["left"] - boxes[0]["right"] == pytest.approx(16, abs=1)
            # A lone card: as wide as a card in a row of two.
            assert alone["cards"][0]["box"]["width"] == pytest.approx(
                (alone["box"]["width"] - 16) / 2, abs=1
            )
            assert alone["cards"][0]["box"]["left"] == pytest.approx(alone["box"]["left"], abs=1)
        else:
            # One per row, each as wide as its block.
            assert tops == sorted(set(tops)), tops
            for b in [*boxes, alone["cards"][0]["box"]]:
                assert b["width"] == pytest.approx(four["box"]["width"], abs=1)
            assert four["box"]["width"] == pytest.approx(width - 32, abs=1)

        first = four["cards"][0]
        assert first["tile"] == [44, 44, "6px"], first["tile"]
        assert [first["title"], first["line"], first["labels"]] == ["20px", "16px", "12px"]
        assert first["radius"] == "14px"
        for c in [*four["cards"], *alone["cards"]]:
            assert c["links"] == 1, "a card holds more than one link"
            assert c["a_point_on_the_line_is_the_link"], (
                "a point on the card's line is not the link"
            )
        assert seen["window"][1] <= seen["window"][0], "the page scrolls sideways"

        # The focus ring stands around the card, 3 px.
        page.keyboard.press("Tab", delay=HELD)
        page.locator(".prose-card a.prose-card-title").first.focus()
        ring = page.evaluate(
            "() => { const c = document.querySelector('.prose-card'); "
            "document.querySelector('.prose-card a').focus({focusVisible: true}); "
            "return getComputedStyle(c).outlineWidth; }"
        )
        assert ring == "3px", ring
    finally:
        page.close()

"""E2E: a dialog of the document editor leaves the author's place where it was (CR-17).

The document editor opens five dialogs — for a picture, a link, a button, a
card and a code. An author works at a place: a block that is selected, some words that
are selected, or a caret between two letters. The rule this file holds:

* closing a dialog WITHOUT a choice — Annuleren, the dialog's close button, a
  click outside it, Escape — leaves that place exactly where it was;
* closing it WITH a choice leaves what the choice made, at that place.

Found on 13 October 2026, on the branch before this rule was built: every one
of the four dialogs it had then lost the place on at least one way of closing, and every
loss ended in the same spot — a caret at the very start of the page's first
paragraph, so that the author's next key went into the text at the top.
Measured there, on a quiet machine, kept of the rounds measured:

* a button selected, its dialog: a click outside 0 of 15 (five arrangements of
  the button); the other three ways and Invoegen 15 of 15 each;
* a range of text selected, the link's dialog: Annuleren, the close button, a
  click outside and Escape 0 of 5 each; Opslaan 5 of 5;
* a caret in text, the picture's, the button's and the card's dialog opened
  from the insert menu and closed with nothing made: a click outside 8 of 10
  each; the other three ways 3 of 3 each;
* a card selected: `test_cards_1770.py` holds that walk (an inner card lost
  its place on all four ways, the first and the last on a click outside).

What moves the browser's selection is NOT identified: no script sets it; it
follows the bare `focus()` with which the kit's dialog handed the focus back
to the editor. The rule does not explain that. It takes the hand-back away
from the dialog: the editor notes the place when a dialog opens and puts it
back itself when the dialog closes.

A limit, said plainly: "stays where it was" is the absence of a change, and no
finite look proves an absence. Each look waits until the browser's selection
has not changed for eight frames; a loss that came later would pass. And the
cells that lost the place only sometimes (a caret, a click outside: about one
round in five) are red on the old code only in some runs — the repeated runs
named in the commit are the evidence for them, not one green run.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.pages.test_cards_1770 import (  # noqa: E402
    _SETTLE,
    EDITOR,
    HELD,
    INSERT,
    _new_page,
    _open,
    _paragraph,
)
from tests_e2e.schermen import pagina_beeld_in_kiezer  # noqa: E402

#: The author's place, read so that a paragraph cut into pieces (a link made in
#: it) does not change the answer: the block that is the selected node, or the
#: selected words with their position counted in characters over the whole
#: block, or the caret's position counted the same way.
PLACE = """() => {
  const root = document.querySelector('#cp-document .tiptap');
  const node = root.querySelector('.ProseMirror-selectednode');
  if (node) return 'selected block: ' + (node.matches('a[data-button]') ? 'button ' + node.textContent : node.tagName.toLowerCase());
  const s = getSelection();
  if (!s.anchorNode || !s.rangeCount) return 'no selection';
  const at = (n, o) => {
    const e = n.nodeType === 1 ? n : n.parentElement;
    if (!root.contains(e)) return 'outside the editor';
    if (e === root) return 'the editor itself, child ' + o;
    let top = e; while (top.parentElement !== root) top = top.parentElement;
    const before = document.createRange(); before.setStart(top, 0); before.setEnd(n, o);
    return 'block ' + ([...root.children].indexOf(top) + 1) + ' character ' + before.toString().length;
  };
  const r = s.getRangeAt(0);
  return s.isCollapsed
    ? 'caret at ' + at(r.startContainer, r.startOffset)
    : 'words ' + JSON.stringify(s.toString()) + ' from ' + at(r.startContainer, r.startOffset) + ' to ' + at(r.endContainer, r.endOffset);
}"""

#: Where some words of the second paragraph stand in the window: [left, right, middle-y].
#: The words are first brought to the middle of the window: on a phone the
#: paragraph stands lower and wraps, and a click by coordinates on a place
#: that is out of view, or under the editor's toolbar, lands on something
#: else. `covered` names what stands at the two points the test will click,
#: when that is not the paragraph itself.
_WORDS_AT = """(words) => {
  const p = document.querySelectorAll('#cp-document .tiptap > p')[1];
  p.scrollIntoView({block: 'center'});
  const text = p.firstChild; const start = text.textContent.indexOf(words);
  const range = document.createRange(); range.setStart(text, start); range.setEnd(text, start + words.length);
  const rects = [...range.getClientRects()];
  const first = rects[0], last = rects[rects.length - 1];
  const hit = (x, y) => { const e = document.elementFromPoint(x, y); return e && p.contains(e) ? null : (e ? e.tagName.toLowerCase() + '.' + e.className : 'nothing'); };
  const from = [first.left + 1, first.top + first.height / 2], to = [last.right - 1, last.top + last.height / 2];
  return {from, to, one_line: rects.length === 1, covered: hit(...from) || hit(...to)};
}"""

TOP = "Boven de rest staat deze zin."
MIDDLE = "Een zin met een woord erin, lang genoeg om in te klikken."
WAYS_WITHOUT_A_CHOICE = ("Annuleren", "the close button", "a click outside", "Escape")


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _button(label: str) -> dict:
    return {
        "type": "button",
        "attrs": {
            "label": label,
            "variant": "secondary",
            "href": f"https://voorbeeld.test/{label}",
        },
    }


def _dialog(state: str) -> str:
    return f"div[x-show='{state}'][role='dialog']"


def _place(page) -> str:
    page.evaluate("() => window.__settle()")
    return page.evaluate(PLACE)


def _close_without_a_choice(page, state: str, way: str) -> None:
    dialog = _dialog(state)
    if way == "Annuleren":
        page.locator(f"{dialog} button", has_text="Annuleren").click()
    elif way == "the close button":
        page.locator(f"{dialog} button[aria-label]").first.click()
    elif way == "a click outside":
        # The dialog stands centred on a backdrop that fills the window; its
        # corner is outside the dialog at every width.
        page.mouse.click(5, 5)
    else:
        page.keyboard.press("Escape", delay=HELD)
    expect(page.locator(dialog)).to_be_hidden()


# ── The places an author can be at, each with the dialog opened from there ──


def _a_button_selected(page) -> tuple[str, str]:
    page.locator(f"{EDITOR} .tiptap a[data-button]", has_text="X").first.click()
    expect(page.locator(_dialog("button"))).to_be_visible()
    return "button", "selected block: button X"


def _words_selected(words: str):
    def opener(page) -> tuple[str, str]:
        at = page.evaluate(_WORDS_AT, words)
        assert at["covered"] is None, (
            f"the words are not free to click: {at['covered']} stands there"
        )
        if " " in words:
            page.mouse.click(*at["from"])
            # The first click's caret stands before the Shift-click extends from
            # it: pressed at once, the Shift-click once left a bare caret
            # (1 of 54 tests in one run, 13 October 2026).
            caret = f"caret at block 2 character {MIDDLE.index(words)}"
            assert _place(page) == caret, (
                "the first click did not put the caret at the words' start"
            )
            page.keyboard.down("Shift")
            page.mouse.click(*at["to"])
            page.keyboard.up("Shift")
        else:
            assert at["one_line"], "the one word is broken over two lines"
            page.mouse.dblclick((at["from"][0] + at["to"][0]) / 2, at["from"][1])
        start = MIDDLE.index(words)
        expected = f"words {words!r} from block 2 character {start} to block 2 character {start + len(words)}".replace(
            "'", '"'
        )
        assert _place(page) == expected, "the test did not select the words it means to"
        page.locator(f"{EDITOR} .de-bar button", has_text="Link").first.click()
        expect(page.locator(_dialog("link"))).to_be_visible()
        return "link", expected

    return opener


def _a_caret_in_text(item: str, state: str):
    def opener(page) -> tuple[str, str]:
        at = page.evaluate(_WORDS_AT, "woord")
        assert at["covered"] is None, f"the word is not free to click: {at['covered']} stands there"
        page.mouse.click(*at["from"])
        expected = f"caret at block 2 character {MIDDLE.index('woord')}"
        assert _place(page) == expected, "the test did not put the caret where it means to"
        page.locator(f"{INSERT} summary").click()
        page.locator(f"{INSERT} button", has_text=item).click()
        expect(page.locator(_dialog(state))).to_be_visible()
        return state, expected

    return opener


PLACES = {
    "a button selected, its dialog": _a_button_selected,
    "a word selected, the link's dialog": _words_selected("woord"),
    "several words selected, the link's dialog": _words_selected("een woord erin"),
    "a caret in text, the picture's dialog": _a_caret_in_text("Afbeelding", "figure"),
    "a caret in text, the button's dialog": _a_caret_in_text("Knop", "button"),
    "a caret in text, the card's dialog": _a_caret_in_text("Kaarten", "card"),
    "a caret in text, the code's dialog": _a_caret_in_text("Code", "codes"),
}


def _page(browser, session, name: str, width: int):
    content = [
        _paragraph(TOP),
        _paragraph(MIDDLE),
        _button("X"),
        _button("Y"),
        _paragraph("Onder."),
    ]
    page_id, _slug = _new_page(name, {"type": "doc", "content": content})
    page = _open(browser, session, page_id, width)
    page.evaluate(_SETTLE)
    return page


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("way", WAYS_WITHOUT_A_CHOICE)
@pytest.mark.parametrize("where", list(PLACES))
def test_closing_a_dialog_without_a_choice_leaves_the_place(setup, where, way, width):
    """Every place, every way of closing without a choice, at both widths: the
    place after is the place before, and nothing changed in what the form
    holds for the document."""
    browser, session = setup
    page = _page(browser, session, f"Plaats {where[:18]} {way[:6]} {width}", width)
    try:
        held = page.locator("#cp-document-input").input_value()
        state, before = PLACES[where](page)
        _close_without_a_choice(page, state, way)
        after = _place(page)
        assert after == before, (
            f"{where}, closed with {way}, at {width} px: the place was [{before}] and is now [{after}]"
        )
        assert page.locator("#cp-document-input").input_value() == held, (
            "closing without a choice changed the document"
        )
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


@pytest.mark.parametrize("way", WAYS_WITHOUT_A_CHOICE)
def test_the_next_key_goes_to_the_place_not_to_the_top_of_the_page(setup, way):
    """What the lost place cost the author: the next key. With a word selected
    and the link's dialog closed without a choice, a letter replaces THAT
    word — and the first paragraph of the page keeps every letter (on the old
    code the letter was typed at the very start of it)."""
    browser, session = setup
    page = _page(browser, session, f"Toets {way[:8]}", 1440)
    try:
        state, _before = PLACES["a word selected, the link's dialog"](page)
        _close_without_a_choice(page, state, way)
        page.evaluate("() => window.__settle()")
        page.keyboard.press("Z", delay=HELD)
        paragraphs = page.locator(f"{EDITOR} .tiptap > p").all_inner_texts()
        assert paragraphs[0] == TOP, f"the key went into the first paragraph: {paragraphs[0]!r}"
        assert paragraphs[1] == MIDDLE.replace("woord", "Z"), (
            f"the key did not replace the selected word: {paragraphs[1]!r}"
        )
    finally:
        page.close()


def test_a_link_saved_leaves_the_words_selected(setup):
    """With a choice: Opslaan makes the link on the selected words, and those
    words are still the selection — read by characters, since the paragraph is
    now cut into pieces around the link."""
    browser, session = setup
    page = _page(browser, session, "Link opslaan", 1440)
    try:
        _state, before = PLACES["several words selected, the link's dialog"](page)
        page.locator("#cp-document-link-url").fill("https://voorbeeld.test/link")
        page.locator(f"{_dialog('link')} button", has_text="Opslaan").click()
        expect(page.locator(_dialog("link"))).to_be_hidden()
        assert _place(page) == before
        link = page.locator(f"{EDITOR} .tiptap > p").nth(1).locator("a")
        assert (
            link.inner_text() == "een woord erin"
            and link.get_attribute("href") == "https://voorbeeld.test/link"
        )
    finally:
        page.close()


def test_a_link_saved_with_the_address_it_had_leaves_the_words_selected(setup):
    """A choice that changes nothing: the link's dialog opened on words that
    are a link already, and Opslaan pressed with the address as it stands. The
    document is equal to the one the dialog opened on, so the rule puts the
    place back as it does after Annuleren — and that is what an author expects
    there: the same words still selected, the link still on them, and nothing
    different in what the form holds."""
    browser, session = setup
    page = _page(browser, session, "Link ongewijzigd", 1440)
    address = "https://voorbeeld.test/link"
    try:
        _state, before = PLACES["several words selected, the link's dialog"](page)
        page.locator("#cp-document-link-url").fill(address)
        page.locator(f"{_dialog('link')} button", has_text="Opslaan").click()
        expect(page.locator(_dialog("link"))).to_be_hidden()
        assert _place(page) == before, "the test did not arrive at a link with its words selected"
        held = page.locator("#cp-document-input").input_value()
        assert address in held

        page.locator(f"{EDITOR} .de-bar button", has_text="Link").first.click()
        expect(page.locator(_dialog("link"))).to_be_visible()
        assert page.locator("#cp-document-link-url").input_value() == address, (
            "the dialog does not show the address the link has"
        )
        page.locator(f"{_dialog('link')} button", has_text="Opslaan").click()
        expect(page.locator(_dialog("link"))).to_be_hidden()

        assert _place(page) == before
        assert page.locator("#cp-document-input").input_value() == held, (
            "a link saved with the address it had changed the document"
        )
        link = page.locator(f"{EDITOR} .tiptap > p").nth(1).locator("a")
        assert link.inner_text() == "een woord erin" and link.get_attribute("href") == address
        # The place put to use: the next key replaces those words, and only those.
        page.keyboard.press("Z", delay=HELD)
        paragraphs = page.locator(f"{EDITOR} .tiptap > p").all_inner_texts()
        assert paragraphs[0] == TOP and paragraphs[1] == MIDDLE.replace("een woord erin", "Z"), (
            paragraphs
        )
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def test_a_picture_a_button_and_a_card_land_at_the_caret(setup):
    """With a choice, from the insert menu: what is made lands where the caret
    stood — in the second paragraph, at the word — and not at the top of the
    page. The first paragraph keeps its words and stays the first block."""
    browser, session = setup

    def made(item: str, state: str, fill) -> list[str]:
        page = _page(browser, session, f"Gemaakt {item}", 1440)
        try:
            PLACES[f"a caret in text, the {'picture' if state == 'figure' else state}'s dialog"](
                page
            )
            fill(page)
            expect(page.locator(_dialog(state))).to_be_hidden()
            page.evaluate("() => window.__settle()")
            return page.evaluate(
                """() => [...document.querySelector('#cp-document .tiptap').children].map(e =>
                     e.tagName === 'P' ? 'p:' + e.textContent : (e.matches('a[data-button]') ? 'button:' + e.textContent
                       : (e.matches('figure') ? 'figure' : (e.matches('[data-cards]') ? 'cards' : e.tagName.toLowerCase()))))"""
            )
        finally:
            page.close()

    def a_picture(page):
        picture = pagina_beeld_in_kiezer(page.locator(_dialog("figure")))
        assert picture.count() == 1, "the seeded picture is not in the picker"
        picture.click()
        page.locator("#cp-document-fig-alt").fill("Een foto")
        page.locator(f"{_dialog('figure')} button", has_text="Invoegen").click()

    def a_button(page):
        page.fill("#cp-document-btn-label", "Nieuw")
        page.locator(f"{_dialog('button')} button", has_text="Een adres buiten de site").click()
        page.locator(f"{_dialog('button')} input[placeholder='https://']").fill(
            "https://voorbeeld.test/n"
        )
        page.locator(f"{_dialog('button')} button", has_text="Invoegen").last.click()

    def a_card(page):
        page.fill("#cp-document-card-title", "Nieuw")
        page.locator(f"{_dialog('card')} button", has_text="Een adres buiten de site").last.click()
        page.locator(f"{_dialog('card')} input[placeholder='https://']").fill(
            "https://voorbeeld.test/n"
        )
        page.locator(f"{_dialog('card')} [data-card-apply]").click()

    head = MIDDLE[: MIDDLE.index("woord")]
    tail = MIDDLE[MIDDLE.index("woord") :]
    for item, state, fill, kind in (
        ("Afbeelding", "figure", a_picture, "figure"),
        ("Knop", "button", a_button, "button:Nieuw"),
        ("Kaarten", "card", a_card, "cards"),
    ):
        blocks = made(item, state, fill)
        assert blocks[0] == f"p:{TOP}", (
            f"{item}: the first paragraph is no longer the first block, whole: {blocks}"
        )
        assert kind in blocks, f"{item}: nothing was made: {blocks}"
        at = blocks.index(kind)
        # Made at the caret: the paragraph's words before the caret stand above it, the rest below.
        assert blocks[at - 1].rstrip() == f"p:{head}".rstrip() and blocks[at + 1] == f"p:{tail}", (
            f"{item} did not land at the caret: {blocks}"
        )

"""E2E: a block the editor selects as a whole keeps its selection (CR-17).

Found on 13 October 2026: a block selected as a whole — a picture, a button —
lost its selection at the author's next key when the blocks on BOTH its sides
were non-editable ones: a picture between two buttons, the middle one of three
pictures, a picture between a button and a cards block (3 of 3 each; kept
where a paragraph or a Kader stood on one side). Within some milliseconds of
the keydown the browser's selection stood at the start of the page's first
paragraph, and the editor followed it — so Delete took a letter at the top of
the page instead of the block. No script moves that selection; WHY the
browser does is not known.

The repair: while a block is selected as a whole, the editor draws one element
of its own right after it — non-editable and empty, taking no room — as
the gap cursor does for its own position. Measured before it was built: with
such an element the selection is kept where nothing else kept it. A card is
held by its block's own attribute instead (an element inside the cards block
would count as a child of it and change its columns) — except the card that
is ALONE in its block, which the attribute does not keep: it gets the
element, inside the block, where with one card it moves nothing.

Three things are held here, every key held as a person holds one:

* in each arrangement that lost it, the block is still selected after a key
  that does nothing, and Delete removes THAT block while the paragraph at the
  top keeps every letter;
* a button between two pictures is still selected after its dialog is closed
  in each of the four ways, and after one more key;
* NOTHING MOVES when a block is selected: the box of every element in the
  editor, measured from the editor's own corner, is the same before and
  while the block is selected — every element, not only the ones expected to
  move. (The element stands between a block and its neighbour, and the
  site's rule "a button right after a button gets 8 px before it" stops
  seeing that neighbour; one rule in the editor's own stylesheet puts the
  8 px back.)

Broken on purpose (13 October 2026), each put back by the reverse edit:
* the extension taken out of the editor → the first two tests red in all
  their 10 cells ("the picture lost its selection at Shift"), and the two
  tests of the page's edge and of the copy;
* the stylesheet's rule for the button after the element made to match
  nothing → "nothing moves" red at the rows of buttons, 1 440 px (the buttons
  after the selected one 8 px to the left);
* the element drawn inside a container of whole blocks too → "nothing moves"
  red at the cards, both widths (one element more in the block; at 1 440 px
  the two cards 384 → 251 px wide);
* the element before the block instead of after it → "nothing moves" red at
  a picture that starts a column, both widths (everything below 8 px down).
* the condition "inside a container only for an only child" turned into "never
  inside a container" → the test of the card alone red in all its cells
  ("lost its selection at Shift"; after a card was removed: "the card that
  stays is not selected");
* the stylesheet's rule that takes the element out of the cards block's rows
  made to match nothing → at 390 px the block grows 16 px ("moves") and the
  card alone is lost; the same rule without its height → the card alone
  lost at both widths;
* the element drawn inside a container whatever the number of children →
  "nothing moves" red at the second card of two (384 → 251 px).
A fifth, and what it taught: a rule that took the element out of the flow
was made to match nothing → everything stayed green; that rule was not
needed and is not in the stylesheet.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.pages.test_cards_1770 import (  # noqa: E402
    _SETTLE,
    CARD,
    DIALOG,
    EDITOR,
    HELD,
    _new_page,
    _open,
    _paragraph,
)
from tests_e2e.pages.test_reading_width_1671 import _photo  # noqa: E402

BUTTON_DIALOG = "div[x-show='button'][role='dialog']"
TOP = "Boven staat deze zin."

#: The editor's selection, in words.
SELECTION = """() => { const s = document.querySelector('#cp-document .tiptap').editor.state.selection;
  return s.node ? 'whole block ' + s.node.type.name + (s.node.attrs.label ? ' ' + s.node.attrs.label : '') + (s.node.attrs.title ? ' ' + s.node.attrs.title : '')
    : 'caret or range in ' + s.$from.parent.type.name + ' at ' + s.$from.parentOffset; }"""

#: The box of EVERY element in the editor (but the editor's own holding
#: element), measured from the editor's own top left corner — the toolbar
#: above the editor may grow a row when a card is selected, and that is not
#: what this is about.
BOXES = """() => { const root = document.querySelector('#cp-document .tiptap'); const o = root.getBoundingClientRect();
  return [...root.querySelectorAll('*')].filter(e => !e.matches('.de-hold')).map((e, i) => { const r = e.getBoundingClientRect();
    return i + ' ' + e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.split(' ')[0] : '') + ' '
      + [Math.round(r.left - o.left), Math.round(r.top - o.top), Math.round(r.width), Math.round(r.height)].join(','); }); }"""


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _figure() -> dict:
    return {"type": "figure", "attrs": {"media_id": _photo(), "alt": "Een probeerbeeld"}}


def _button(label: str) -> dict:
    return {
        "type": "button",
        "attrs": {
            "label": label,
            "variant": "secondary",
            "href": f"https://voorbeeld.test/{label}",
        },
    }


def _cards(*titles: str) -> dict:
    return {
        "type": "cards",
        "content": [
            {"type": "card", "attrs": {"title": t, "href": f"https://voorbeeld.test/{t}"}}
            for t in titles
        ],
    }


def _callout() -> dict:
    return {"type": "callout", "content": [{"type": "text", "text": "Een kader."}]}


def _columns(first: list, second: list) -> dict:
    return {
        "type": "columns",
        "content": [{"type": "column", "content": first}, {"type": "column", "content": second}],
    }


def _settle(page) -> None:
    """Until the browser's selection has not changed for eight frames in a
    row — the loss this file is about comes some milliseconds after a key, as
    a change of that selection. Counted in frames, not on a clock."""
    page.evaluate(_SETTLE)
    page.evaluate("() => window.__settle()")


def _look(page) -> str:
    _settle(page)
    return page.evaluate(SELECTION)


#: The arrangements that lost the selection: what stands in the page, and
#: which picture is the block between two non-editable blocks.
BETWEEN = {
    "a picture between two buttons": (lambda: [_button("A"), _figure(), _button("B")], 0, 0),
    "the middle one of three pictures": (lambda: [_figure(), _figure(), _figure()], 1, 2),
    "a picture between a button and a cards block": (
        lambda: [_button("A"), _figure(), _cards("K1", "K2")],
        0,
        0,
    ),
}


@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("where", list(BETWEEN))
def test_a_block_between_two_non_editable_blocks_keeps_its_selection(setup, where, width):
    browser, session = setup
    blocks, which, pictures_left = BETWEEN[where]
    content = [_paragraph(TOP), *blocks(), _paragraph("Onder.")]
    page_id, _slug = _new_page(
        f"Blok houdt {where[:22]} {width}", {"type": "doc", "content": content}
    )
    page = _open(browser, session, page_id, width)
    try:
        pictures = page.locator(f"{EDITOR} .tiptap figure")
        pictures.nth(which).click()
        assert _look(page) == "whole block figure", (
            "the test did not select the picture it means to"
        )

        # Keys that do nothing: the picture is still the selection.
        for key in ("Shift", "Control", "Escape"):
            page.keyboard.press(key, delay=HELD)
            assert _look(page) == "whole block figure", (
                f"{where}, at {width} px: the picture lost its selection at {key}"
            )
        assert pictures.nth(which).evaluate("e => e.classList.contains('ProseMirror-selectednode')")

        # The key that does something goes to THAT block, not to the top of the page.
        page.keyboard.press("Delete", delay=HELD)
        expect(pictures).to_have_count(pictures_left)
        assert page.locator(f"{EDITOR} .tiptap > p").first.inner_text() == TOP, (
            "Delete took a letter of the paragraph at the top"
        )
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


@pytest.mark.parametrize("way", ["Annuleren", "the close button", "a click outside", "Escape"])
def test_a_button_between_two_pictures_keeps_its_selection_after_its_dialog(setup, way):
    """The one such block with a dialog of its own: closed in each of the four
    ways, the button is still selected, and still after one more key. (Without
    the element: selected when the dialog was gone, lost at the next key; with
    Escape lost at once, the Escape's own key-up being that next key.)"""
    browser, session = setup
    content = [_paragraph(TOP), _figure(), _button("Knop"), _figure(), _paragraph("Onder.")]
    page_id, _slug = _new_page(f"Knop houdt {way[:8]}", {"type": "doc", "content": content})
    page = _open(browser, session, page_id, 1440)
    try:
        page.locator(f"{EDITOR} .tiptap a[data-button]").click()
        expect(page.locator(BUTTON_DIALOG)).to_be_visible()
        if way == "Annuleren":
            page.locator(f"{BUTTON_DIALOG} button", has_text="Annuleren").click()
        elif way == "the close button":
            page.locator(f"{BUTTON_DIALOG} button[aria-label]").first.click()
        elif way == "a click outside":
            page.mouse.click(5, 5)
        else:
            page.keyboard.press("Escape", delay=HELD)
        expect(page.locator(BUTTON_DIALOG)).to_be_hidden()
        assert _look(page) == "whole block button Knop", (
            f"lost its selection when closed with {way}"
        )
        page.keyboard.press("Shift", delay=HELD)
        assert _look(page) == "whole block button Knop", (
            f"lost its selection at the key after {way}"
        )
        assert page.locator(f"{EDITOR} .tiptap > p").first.inner_text() == TOP
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


#: What is selected in each arrangement of the test below: (the page's blocks,
#: the selector of the block, its index, what the editor then says it holds).
STILL = {
    "a picture between two paragraphs": (lambda: [_figure()], "figure", 0, "whole block figure"),
    "a picture between two buttons": (
        lambda: [_button("A"), _figure(), _button("B")],
        "figure",
        0,
        "whole block figure",
    ),
    "the middle one of three pictures": (
        lambda: [_figure(), _figure(), _figure()],
        "figure",
        1,
        "whole block figure",
    ),
    "the first of three buttons in a row": (
        lambda: [_button("A"), _button("B"), _button("C")],
        "a[data-button]",
        0,
        "whole block button A",
    ),
    "the middle of three buttons in a row": (
        lambda: [_button("A"), _button("B"), _button("C")],
        "a[data-button]",
        1,
        "whole block button B",
    ),
    "the last of three buttons in a row": (
        lambda: [_button("A"), _button("B"), _button("C")],
        "a[data-button]",
        2,
        "whole block button C",
    ),
    "a picture that starts a column, a button after it": (
        lambda: [_columns([_figure(), _button("A")], [_paragraph("Rechts.")])],
        "figure",
        0,
        "whole block figure",
    ),
    "a button that starts a column, a button after it": (
        lambda: [_columns([_button("A"), _button("B")], [_paragraph("Rechts.")])],
        "a[data-button]",
        0,
        "whole block button A",
    ),
    "a picture between two Kader blocks": (
        lambda: [_callout(), _figure(), _callout()],
        "figure",
        0,
        "whole block figure",
    ),
    "the only card of its block": (
        lambda: [_cards("K1")],
        "[data-card]",
        0,
        "whole block card K1",
    ),
    "the second card of two": (
        lambda: [_cards("K1", "K2")],
        "[data-card]",
        1,
        "whole block card K2",
    ),
    "the middle card of three": (
        lambda: [_cards("K1", "K2", "K3")],
        "[data-card]",
        1,
        "whole block card K2",
    ),
    "a picture between a button and a cards block": (
        lambda: [_button("A"), _figure(), _cards("K1", "K2")],
        "figure",
        0,
        "whole block figure",
    ),
}


@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("where", list(STILL))
def test_nothing_moves_when_a_block_is_selected(setup, where, width):
    """Every element's box in the editor is the same before and while a block
    is selected — every element, compared as a whole list."""
    browser, session = setup
    blocks, selector, index, holds = STILL[where]
    content = [_paragraph(TOP), *blocks(), _paragraph("Onder.")]
    page_id, _slug = _new_page(
        f"Niets schuift {where[:24]} {width}", {"type": "doc", "content": content}
    )
    page = _open(browser, session, page_id, width)
    try:
        # The author in the editor, nothing selected as a whole yet.
        page.locator(f"{EDITOR} .tiptap > p").last.click()
        _settle(page)
        before = page.evaluate(BOXES)
        assert len(before) > 3, "the look found no elements in the editor"

        page.locator(f"{EDITOR} .tiptap {selector}").nth(index).click()
        dialog = (
            BUTTON_DIALOG
            if selector == "a[data-button]"
            else (DIALOG if selector == "[data-card]" else None)
        )
        if dialog:
            expect(page.locator(dialog)).to_be_visible()
            page.locator(f"{dialog} button", has_text="Annuleren").click()
            expect(page.locator(dialog)).to_be_hidden()
        assert _look(page) == holds, "the test did not select the block it means to"

        while_selected = page.evaluate(BOXES)
        moved = [f"{a} -> {b}" for a, b in zip(before, while_selected) if a != b]
        assert len(before) == len(while_selected), (
            f"{where}, at {width} px: the editor holds {len(while_selected)} elements while the block is "
            f"selected, {len(before)} before"
        )
        assert not moved, (
            f"{where}, at {width} px: selecting the block moves {len(moved)} elements: {moved[:6]}"
        )
        assert page.locator(CARD).count() == len(
            page.locator(f"{EDITOR} .tiptap [data-card]").all()
        )
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def test_a_block_that_ends_or_starts_the_page_keeps_its_selection(setup):
    """Where the element stands for a block with nothing after it, and for one
    with nothing before it: a picture between a button and the END of the
    page, and a picture that STARTS the page with a button after it. The
    first is selected by a click; the second by ArrowLeft from the text below
    (a click on a page's first block is the library's own matter: the editor
    already holds that block when the page opens). Kept after a key, and
    nothing in the editor moves."""
    browser, session = setup
    for name, content, select in (
        (
            "a picture that ends the page",
            [_paragraph(TOP), _button("A"), _figure()],
            lambda page: page.locator(f"{EDITOR} .tiptap figure").click(),
        ),
        (
            "a picture that starts the page",
            [_figure(), _button("A"), _paragraph(TOP)],
            lambda page: (
                page.locator(f"{EDITOR} .tiptap > p").first.click(),
                page.keyboard.press("Home", delay=HELD),
                # The button, the gap between the two blocks, the picture.
                page.keyboard.press("ArrowLeft", delay=HELD),
                page.keyboard.press("ArrowLeft", delay=HELD),
                page.keyboard.press("ArrowLeft", delay=HELD),
            ),
        ),
    ):
        page_id, _slug = _new_page(f"Rand {name[10:24]}", {"type": "doc", "content": content})
        page = _open(browser, session, page_id, 1440)
        try:
            page.locator(f"{EDITOR} .tiptap > p").first.click()
            _settle(page)
            before = page.evaluate(BOXES)
            select(page)
            assert _look(page) == "whole block figure", (
                f"{name}: the test did not select the picture"
            )
            assert page.evaluate(BOXES) == before, f"{name}: selecting it moves something"
            page.keyboard.press("Shift", delay=HELD)
            assert _look(page) == "whole block figure", f"{name}: lost its selection at Shift"
            assert page.locator(f"{EDITOR} .tiptap .de-hold").count() == 1
            assert page.errors == [], f"the screen throws: {page.errors}"
        finally:
            page.close()


def test_the_element_does_not_travel_with_what_is_copied(setup):
    """The element is the editor's own and is no part of the document: what
    the author copies with a block selected carries the block and not the
    element, and neither does what the form holds for the document."""
    browser, session = setup
    content = [_paragraph(TOP), _button("A"), _figure(), _button("B"), _paragraph("Onder.")]
    page_id, _slug = _new_page("Kopie zonder element", {"type": "doc", "content": content})
    page = _open(browser, session, page_id, 1440)
    try:
        page.evaluate(
            """() => { window.__copied = null; document.addEventListener('copy', e => {
                 window.__copied = e.clipboardData ? e.clipboardData.getData('text/html') : 'no clipboard data'; }); }"""
        )
        page.locator(f"{EDITOR} .tiptap figure").click()
        assert _look(page) == "whole block figure"
        assert page.locator(f"{EDITOR} .tiptap .de-hold").count() == 1, "the element is not drawn"
        page.keyboard.press("Control+c", delay=HELD)
        page.wait_for_function("() => window.__copied !== null")
        copied = page.evaluate("() => window.__copied")
        assert copied and "<figure" in copied, f"the copy does not carry the picture: {copied!r}"
        assert "de-hold" not in copied, "the editor's own element travels in the copied markup"
        assert "de-hold" not in page.locator("#cp-document-input").input_value()
        assert _look(page) == "whole block figure"
    finally:
        page.close()


#: The ways an author gets a card that is alone in its block: (the cards the
#: block starts with, how many times Delete is pressed on the selected first
#: card, the card that is then alone).
ALONE = {
    "a block made with one card": (("K1",), 0, "K1"),
    "a block of two, one removed": (("K1", "K2"), 1, "K2"),
    "a block of three, two removed": (("K1", "K2", "K3"), 2, "K3"),
}


@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("how", list(ALONE))
def test_a_card_alone_in_its_block_keeps_its_selection(setup, how, width):
    """The one position the cards block's attribute does not cover, and where
    it bit: the test that removes cards one by one lost the card that was
    left, under load (18 of 40 at the removal that leaves one; 28 of 60
    rounds of the whole test), and on a quiet machine the only card of a
    block lost its selection at the next key, 5 of 5.

    Here: the card that stays is selected, with the cards menu there; it is
    still selected after keys that do nothing; and Delete removes it — the
    block goes with its last card, the caret stands at the start of the
    paragraph below, the menu is gone, and both paragraphs keep every
    letter (before the repair that Delete took the first letter of the page).
    """
    browser, session = setup
    titles, removals, stays = ALONE[how]
    content = [_paragraph(TOP), _cards(*titles), _paragraph("Onder de kaarten.")]
    page_id, _slug = _new_page(
        f"Kaart alleen {len(titles)} {width}", {"type": "doc", "content": content}
    )
    page = _open(browser, session, page_id, width)
    menu = page.locator(f"{EDITOR} details.de-menu-cards")
    try:
        page.locator(CARD).first.click()
        expect(page.locator(DIALOG)).to_be_visible()
        page.locator(f"{DIALOG} button", has_text="Annuleren").click()
        expect(page.locator(DIALOG)).to_be_hidden()
        for _ in range(removals):
            page.keyboard.press("Delete", delay=HELD)
            _settle(page)
        expect(page.locator(CARD)).to_have_count(1)
        assert _look(page) == f"whole block card {stays}", (
            f"{how}: the card that stays is not selected"
        )
        expect(menu).to_be_visible()

        for key in ("Shift", "Control", "Escape"):
            page.keyboard.press(key, delay=HELD)
            assert _look(page) == f"whole block card {stays}", (
                f"{how}, at {width} px: the card alone lost its selection at {key}"
            )
        expect(menu).to_be_visible()

        page.keyboard.press("Delete", delay=HELD)
        expect(page.locator(CARD)).to_have_count(0)
        expect(page.locator(f"{EDITOR} .tiptap [data-cards]")).to_have_count(0)
        assert _look(page) == "caret or range in paragraph at 0"
        expect(menu).to_be_hidden()
        assert page.locator(f"{EDITOR} .tiptap > p").all_inner_texts() == [
            TOP,
            "Onder de kaarten.",
        ], "removing the last card changed the text of the page"
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()

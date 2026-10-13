"""E2E: a selected block of the document editor shows that it is selected (CR-17).

The editor selects some blocks as a whole — a card, a button, a picture. Koen,
13 October 2026, to the question whether such a block gets a visible edge
(one rule for every block, the kit's blue focus ring) or stays without a
mark: "A ivm geselecteerd blok". Until then nothing showed it; since the
cards block lets the arrows walk from card to card, Delete removed a card the
author could not see was selected.

Read from the rendered page, at 390 and 1 440 px:

* nothing carries the ring while nothing is selected;
* a selected card, a selected button and a selected picture each carry it —
  3 px, solid, 3 px away, in the kit's `focus` token — and no other block
  does: exactly one ring on the page;
* after an arrow key the ring stands on the next card and on no other;
* the ring is not cut off: with its 6 px it stays inside the editor's box.

The colour is not written here as a number: the page is asked what its own
`focus` token resolves to, on an element the test adds for the question.

Broken on purpose (13 October 2026), each put back by the reverse edit, red
at both widths: the rule's selector made to match nothing → "the selected
card K2 carries no ring"; the rule narrowed to cards (`[data-card]` added to
its selector) → "the selected picture carries no ring"; the ring 2 px wide →
("solid", "2px", "3px") is not ("solid", "3px", "3px"); the ring in the
brand blue instead of the focus token → "the ring of card K2 is rgb(37, 78,
115), the kit's focus token is rgb(25, 95, 157)".
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.pages.test_cards_1770 import (  # noqa: E402
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

#: Every block the editor can select as a whole, with what its outline is, and
#: the editor's box. `ringed` are the blocks whose outline is drawn at all.
RINGS = """() => {
  const root = document.querySelector('#cp-document .tiptap');
  const probe = document.createElement('span');
  probe.style.outline = '3px solid rgb(var(--c-focus))';
  root.parentElement.appendChild(probe);
  const token = getComputedStyle(probe).outlineColor;
  probe.remove();
  const name = e => e.matches('[data-card]') ? 'card ' + e.querySelector('.prose-card-title').textContent
    : (e.matches('a[data-button]') ? 'button ' + e.textContent.trim() : (e.matches('figure') ? 'picture' : e.tagName.toLowerCase()));
  const surface = root.closest('.de-surface').getBoundingClientRect();
  const blocks = [...root.querySelectorAll('[data-card], a[data-button], figure')].map(e => {
    const s = getComputedStyle(e); const r = e.getBoundingClientRect();
    return {name: name(e), selected: e.classList.contains('ProseMirror-selectednode'),
            style: s.outlineStyle, width: s.outlineWidth, offset: s.outlineOffset, colour: s.outlineColor,
            left: r.left, right: r.right};
  });
  return {token, surface: [surface.left, surface.right], blocks,
          ringed: blocks.filter(b => b.style !== 'none' && b.width !== '0px').map(b => b.name),
          selected: [...root.querySelectorAll('.ProseMirror-selectednode')].map(name)};
}"""


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _the_one_ring(seen: dict, name: str, width: int) -> None:
    assert seen["selected"] == [name], (
        f"at {width} px the editor selects {seen['selected']}, not {name}"
    )
    assert seen["ringed"] == [name], (
        f"at {width} px the selected {name} carries no ring, or another block carries one: {seen['ringed']}"
    )
    block = next(b for b in seen["blocks"] if b["name"] == name)
    assert (block["style"], block["width"], block["offset"]) == ("solid", "3px", "3px"), block
    assert block["colour"] == seen["token"], (
        f"the ring of {name} is {block['colour']}, the kit's focus token is {seen['token']}"
    )
    # Not cut off: the ring reaches 6 px beyond the block, the editor's box hides what leaves it.
    left, right = seen["surface"]
    assert block["left"] - 6 >= left and block["right"] + 6 <= right, (
        f"the ring of {name} leaves the editor's box at {width} px: block {block['left']:.0f}..{block['right']:.0f}, "
        f"box {left:.0f}..{right:.0f}"
    )


@pytest.mark.parametrize("width", [390, 1440])
def test_a_selected_block_carries_the_ring_and_no_other_does(setup, width):
    browser, session = setup
    document = {
        "type": "doc",
        "content": [
            _paragraph("Boven de blokken."),
            {
                "type": "button",
                "attrs": {
                    "label": "Knop",
                    "variant": "secondary",
                    "href": "https://voorbeeld.test/k",
                },
            },
            # A paragraph on each side of the picture, on purpose: a block
            # that stands between two non-editable blocks (a picture between
            # two buttons, or between a button and the cards) loses its
            # selection at the author's next key — measured on 13 October
            # 2026, 3 of 3 in each such arrangement, and open: this test is
            # about the ring a selected block carries, not about that.
            _paragraph("Tussen de knop en de afbeelding."),
            {"type": "figure", "attrs": {"media_id": _photo(), "alt": "Een probeerbeeld"}},
            _paragraph("Tussen de afbeelding en de kaarten."),
            {
                "type": "cards",
                "content": [
                    {"type": "card", "attrs": {"title": t, "href": f"https://voorbeeld.test/{t}"}}
                    for t in ("K1", "K2", "K3")
                ],
            },
            _paragraph("Onder de blokken."),
        ],
    }
    page_id, _slug = _new_page(f"Geselecteerd blok {width}", document)
    page = _open(browser, session, page_id, width)
    try:
        seen = page.evaluate(RINGS)
        # The look itself, before its answer: it finds the five blocks it is about.
        assert [b["name"] for b in seen["blocks"]] == [
            "button Knop",
            "picture",
            "card K1",
            "card K2",
            "card K3",
        ]
        assert seen["token"].startswith("rgb"), (
            f"the page does not resolve the focus token: {seen['token']}"
        )
        assert seen["ringed"] == [] and seen["selected"] == [], (
            "a block carries a ring while nothing is selected"
        )

        # A card, selected by a click (its dialog closed with Escape).
        page.locator(CARD).nth(1).click()
        expect(page.locator(DIALOG)).to_be_visible()
        page.keyboard.press("Escape", delay=HELD)
        expect(page.locator(DIALOG)).to_be_hidden()
        _the_one_ring(page.evaluate(RINGS), "card K2", width)

        # The arrows move the ring with the selection: the next card, the one before, never two.
        page.keyboard.press("ArrowRight", delay=HELD)
        _the_one_ring(page.evaluate(RINGS), "card K3", width)
        page.keyboard.press("ArrowLeft", delay=HELD)
        page.keyboard.press("ArrowLeft", delay=HELD)
        _the_one_ring(page.evaluate(RINGS), "card K1", width)

        # The picture, selected by a click — and still ringed after a key
        # that does nothing.
        page.locator(f"{EDITOR} .tiptap figure").click()
        _the_one_ring(page.evaluate(RINGS), "picture", width)
        page.keyboard.press("Shift", delay=HELD)
        _the_one_ring(page.evaluate(RINGS), "picture", width)

        # The button, selected by a click (its dialog closed with Escape).
        page.locator(f"{EDITOR} .tiptap a[data-button]").click()
        expect(page.locator(BUTTON_DIALOG)).to_be_visible()
        page.keyboard.press("Escape", delay=HELD)
        expect(page.locator(BUTTON_DIALOG)).to_be_hidden()
        _the_one_ring(page.evaluate(RINGS), "button Knop", width)

        # Back in the text: no block is selected, no ring is left behind.
        page.locator(f"{EDITOR} .tiptap > p").first.click()
        seen = page.evaluate(RINGS)
        assert seen["ringed"] == [] and seen["selected"] == [], (
            f"a ring is left behind: {seen['ringed']}"
        )
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()

"""E2E: the head of the page screen gives its fields the room of the form grid
(#1983).

The page screen handed the kit's form grid two hand-made grids — one for
Titel and Webadres, one for the three switches. Each was ONE cell of the form
grid, so two fields shared one field column: measured on 14 October 2026, the
Webadres input was 72 px wide at 390 px and 91 px at 1 440 px where its text
needed 132, and "Toon in de voettekst" stood on three lines at both widths.

Now the fields are the kit's own, straight in the form grid. Read from the
rendered page: at 1 440 px a web address of thirty characters fits its input
and no switch's label takes more than one line; at 390 px the input is as
wide as the form grid and no label takes more than two lines; the page is no
wider than the window.

Broken on purpose (14 October 2026), put back by the reverse edit: the five
fields (seven since #2024) wrapped in a hand-made grid again → both widths red
on "the form grid does not hold the five fields", with the input 72 px wide in a grid of 324 at
390 px.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.pages.test_cards_1770 import _new_page, _open, _paragraph  # noqa: E402

THIRTY = "een-webadres-van-dertig-tekens"
HEAD = """() => {
  const input = document.querySelector('#cp-slug');
  const grid = input.closest('[data-form-grid]');
  const lines = [...grid.querySelectorAll('[data-kind="switch"] label')].map(label => {
    const text = [...label.querySelectorAll('span')]
      .filter(s => s.textContent.trim() && !s.children.length).pop();
    const box = text.getBoundingClientRect();
    return [text.textContent.trim(), Math.round(box.height / parseFloat(getComputedStyle(text).lineHeight))];
  });
  return {
    'input width': Math.round(input.getBoundingClientRect().width),
    'text needs': input.scrollWidth,
    'input shows': input.clientWidth,
    'form grid width': Math.round(grid.getBoundingClientRect().width),
    'fields in the grid': grid.querySelectorAll(':scope > [data-field]').length,
    'label lines': lines,
    'page wider than the window by': document.documentElement.scrollWidth - innerWidth,
  };
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


@pytest.mark.parametrize(("width", "most_lines"), [(390, 2), (1440, 1)])
def test_the_head_gives_its_fields_the_form_grid(setup, width, most_lines):
    browser, session = setup
    assert len(THIRTY) == 30
    page_id, _slug = _new_page(f"Kop {width}", {"type": "doc", "content": [_paragraph("Tekst.")]})
    page = _open(browser, session, page_id, width)
    try:
        page.locator("#cp-slug").fill(THIRTY)
        seen = page.evaluate(HEAD)
        # Seven since #2024 (CR-17 phase 6): Naam in het menu and Onder sectie,
        # which shows because the seeded site has pages to stand under.
        assert seen["fields in the grid"] == 7, (
            f"the form grid does not hold the seven fields: {seen}"
        )
        assert len(seen["label lines"]) == 3, f"the test did not find the three switches: {seen}"
        if width == 1440:
            assert seen["text needs"] <= seen["input shows"], (
                f"the web address does not fit its input: {seen}"
            )
        else:
            assert seen["input width"] == seen["form grid width"], (
                f"the input is not as wide as the form grid: {seen}"
            )
        too_long = [label for label in seen["label lines"] if label[1] > most_lines]
        assert not too_long, f"a switch's label takes more than {most_lines} line(s): {seen}"
        assert seen["page wider than the window by"] <= 0, seen
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()

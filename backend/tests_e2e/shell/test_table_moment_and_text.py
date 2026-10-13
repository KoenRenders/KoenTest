"""E2E: the kit table's parts for a moment and for free text (#1915).

Read on the kit page's own example (`[data-kit-moment-text]`): a list of
events with the columns Wanneer (`moment`), Status, Aantal and Opmerking
(`text`); its second row has no text.

- **A moment fits its column.** A `date` column is 112 px and `short_datetime`
  with its year is wider, so the minutes stood in the next column. The test
  writes the widest moment there is — ten times each digit — and asks its right
  edge inside the cell's own padding, at 1 100 and at 1 440 px.
- **Free text takes the rest on a desktop**: the widest column, and a long
  sentence on fewer lines than in a column of a fixed share.
- **Free text stands in the stacked row on a phone**, as its last line, and an
  empty one leaves nothing: no line and no gap.

Broken on purpose (12 October 2026), each put back by the reverse edit — the
widths were classes then (`w-[152px]`); since #1927 they are the macro's
lengths (`'moment': '152px'`) and the last column takes the rest:
- the moment's `w-[152px]` made the `date` part's `w-[112px]` → the first test
  red at both widths ("the moment 00-00-0000 00:00 ends … past its cell");
- the moment's width taken out altogether → the column takes half of the rest
  and the moment fits, so that test stays green; the desktop test is the one
  that goes red (moment 463 px, text 463 px);
- the stacked rule of `[data-cell="text"]` out of `scripts/build-css.sh` → the
  phone test red ("the text is not a line of its own");
- the `:empty` rule out → the phone test red ("an empty text is shown").
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, pagina_klaar  # noqa: E402

PAGE = "/admin/design-system"
#: The cell's `px-3`.
PADDING = 12

#: What the example measures. Boxes are [left, right, top, bottom]; `text` is
#: the box of a cell's content, not of the cell.
MEASURE = """() => {
  const root = document.querySelector('[data-kit-moment-text]');
  const table = root.querySelector('table');
  const box = e => { const b = e.getBoundingClientRect(); return [b.left, b.right, b.top, b.bottom]; };
  const text = td => { const r = document.createRange(); r.selectNodeContents(td); return box(r); };
  const first = table.querySelector('td[data-cell="moment"]');
  const keep = first.textContent;
  const moments = {};
  for (const d of '0123456789') {
    first.textContent = `${d}${d}-${d}${d}-${d}${d}${d}${d} ${d}${d}:${d}${d}`;
    moments[first.textContent] = text(first);
  }
  first.textContent = keep;
  const rows = [...table.querySelectorAll('tbody tr')].map(tr => {
    const cells = {};
    for (const td of tr.children) cells[td.dataset.cell] = {shown: td.checkVisibility(), box: box(td), text: text(td)};
    return {box: box(tr), cells};
  });
  const long = table.querySelector('td[data-cell="text"]');
  const head = table.querySelector('th[data-cell="text"]');
  const lines = () => Math.round(text(long)[3] - text(long)[2]);
  const free = lines();
  head.style.width = '24%';
  const fixed = lines();
  head.style.width = '';
  return {
    heads: Object.fromEntries([...table.querySelectorAll('th')].map(th => [th.dataset.cell, box(th)])),
    moments, moment_cell: box(first), rows,
    long_text_height: {free, fixed},
    window: [window.innerWidth, document.documentElement.scrollWidth],
  };
}"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def measure(browser, width: int) -> dict:
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        login_als_admin(page, email, make_session_value(email))
        page.goto(PAGE)
        pagina_klaar(page)
        page.wait_for_selector("[data-kit-moment-text] table")
        return page.evaluate(MEASURE)
    finally:
        page.close()


@pytest.mark.parametrize("width", (1100, 1440))
def test_the_widest_moment_fits_its_column(browser, width):
    seen = measure(browser, width)
    assert len(seen["moments"]) == 10
    cell_right = seen["moment_cell"][1]
    next_left = seen["heads"]["status"][0]
    for moment, (_left, right, _top, _bottom) in seen["moments"].items():
        assert right <= cell_right - PADDING + 0.5, (
            f"at {width} px the moment {moment} ends at {right:.1f}, past its cell "
            f"({cell_right:.1f}, with {PADDING} px of padding)"
        )
        assert right < next_left
    assert seen["window"][1] <= seen["window"][0]


def test_free_text_takes_the_rest_on_a_desktop(browser):
    seen = measure(browser, 1440)
    widths = {part: right - left for part, (left, right, _t, _b) in seen["heads"].items()}
    assert widths["text"] == max(widths.values()), f"the text column is not the widest: {widths}"
    assert widths["text"] > 2 * max(widths["moment"], widths["status"], widths["amount"]), widths
    height = seen["long_text_height"]
    assert height["free"] < height["fixed"], (
        f"the long sentence is {height['free']} px high in the free column "
        f"and {height['fixed']} px in a column of 24 %"
    )


def test_free_text_stands_last_in_the_stacked_row_and_an_empty_one_leaves_nothing(browser):
    seen = measure(browser, 390)
    filled, empty, short = seen["rows"]

    for row in (filled, short):
        cells = row["cells"]
        assert cells["text"]["shown"], "the text is not shown in the stacked row"
        above = max(cells[part]["box"][3] for part in ("moment", "status", "amount"))
        assert cells["text"]["box"][2] >= above, "the text does not stand under the rest of its row"
        # A line of its own: from the row's left edge to its right edge, as the
        # moment under the status is.
        assert cells["text"]["box"][0] == pytest.approx(cells["moment"]["box"][0], abs=1)
        assert cells["text"]["box"][1] == pytest.approx(cells["moment"]["box"][1], abs=1), (
            "the text is not a line of its own in the stacked row"
        )
        assert cells["text"]["text"][1] <= row["box"][1]
        # The moment stands where a date stands beside an amount: under the status.
        assert cells["moment"]["shown"]
        assert cells["moment"]["box"][2] >= cells["status"]["box"][3]

    assert not empty["cells"]["text"]["shown"], "an empty text is shown"
    # Against the first row, which has a bottom line like the empty one (the
    # table's last row has none).
    height = {
        name: row["box"][3] - row["box"][2] for name, row in (("empty", empty), ("filled", filled))
    }
    text = filled["cells"]["text"]["box"][3] - filled["cells"]["text"]["box"][2]
    gap = filled["cells"]["text"]["box"][2] - filled["cells"]["moment"]["box"][3]
    assert text > 10 and gap > 0
    left_over = height["empty"] - (height["filled"] - text - gap)
    assert left_over == pytest.approx(0, abs=0.5), (
        f"a row without text is {height['empty']:.0f} px, one with {text:.0f} px of text "
        f"{height['filled']:.0f} px: the empty one keeps {left_over:.0f} px for nothing"
    )
    assert seen["window"][1] <= seen["window"][0], "the page scrolls sideways at 390 px"

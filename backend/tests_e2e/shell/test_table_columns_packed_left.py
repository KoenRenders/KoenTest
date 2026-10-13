"""E2E: the kit table's columns stand at their own width, packed left, and the
last column takes the rest (#1927; Koen, 12 October 2026, on a list at
1 920 px: "vooral alles naar links").

Read on the three lists that stand on the kit's table — Leden, Personen,
Betalingen — at 1 100, 1 440 and 1 920 px:

- **the last column ends at the frame's edge**, so the row lines run on, and
  nothing scrolls sideways;
- **the name is 380 px, or what the other columns leave**: 380 px on Leden at
  every width, and on Betalingen at 1 440 px less than that, with the last
  column at its own 156 px — the name gives way before anything overflows —
  and at 1 100 px the same, where the optional column that left gave its room
  back to the name;
- **the white space falls behind the last column**: on Leden at 1 920 px the
  Personen head starts where the name ends, not at the frame's right;
- **a column head never wraps**: one line, and its label inside its cell.

Broken on purpose (13 October 2026), each put back and the css rebuilt:
- the name's width rule out of `scripts/build-css.sh` → the name shares the
  rest ("/admin/leden at 1100 px: the name is 493 px, wider than its 380"; "the
  second head starts at 1020, the frame at 256");
- that rule without its `min()` — the name never gives way → "Betalingen at
  1100 px has room for the whole name";
- the rule that gives an optional column's room back out → "Betalingen at
  1100 px: the name left the actions 260 px, not their 156";
- Personen's Aangemaakt at 40 px → "head 'extra': its label ends at 926.625,
  the cell at 881.625".
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, pagina_klaar  # noqa: E402

LISTS = ("/admin/leden", "/admin/personen?zicht=alle", "/admin/betalingen")
WIDTHS = (1100, 1440, 1920)
#: The kit's width of a name, and of the actions.
NAME = 380
ACTIONS = 156

#: Boxes are [left, right]; `label` is the box of the head's content.
MEASURE = """() => {
  const frame = document.querySelector('[data-table-frame]');
  const side = e => { const b = e.getBoundingClientRect(); return [b.left, b.right]; };
  const label = th => { const r = document.createRange(); r.selectNodeContents(th); return side(r); };
  const heads = [...frame.querySelectorAll('thead th')].filter(th => th.checkVisibility()).map(th => ({
    cell: th.dataset.cell, box: side(th), label: label(th), height: th.getBoundingClientRect().height,
    last: th.hasAttribute('data-last-head'),
  }));
  const row = frame.querySelector('tr[data-row]');
  return {
    frame: side(frame), heads,
    last_cell: side(row.lastElementChild),
    window: [window.innerWidth, document.documentElement.scrollWidth],
  };
}"""


@pytest.fixture(scope="module")
def measured():
    """{(list, width): what the list measures there}, each after a full load."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    found = {}
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        login_als_admin(page, email, make_session_value(email))
        for path in LISTS:
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 900})
                page.goto(path)
                pagina_klaar(page)
                page.wait_for_selector("[data-table-frame] tr[data-row]")
                found[path, width] = page.evaluate(MEASURE)
        browser.close()
    return found


def _width(box):
    return box[1] - box[0]


def test_the_last_column_ends_at_the_frames_edge(measured):
    for (path, width), m in measured.items():
        where = f"{path} at {width} px"
        assert m["window"][1] <= m["window"][0], f"{where} scrolls sideways: {m['window']}"
        last = m["heads"][-1]
        assert last["last"], f"{where}: the last visible head is not the table's last column"
        # the frame's border is 1 px
        assert abs(last["box"][1] - (m["frame"][1] - 1)) <= 1, (
            f"{where}: the last head ends at {last['box'][1]}, the frame at {m['frame'][1]}"
        )
        assert abs(m["last_cell"][1] - (m["frame"][1] - 1)) <= 1, (
            f"{where}: the row's last cell ends at {m['last_cell'][1]}, the frame at {m['frame'][1]}"
        )


def test_the_name_stands_at_its_width_or_at_what_the_others_leave(measured):
    for (path, width), m in measured.items():
        name = m["heads"][0]
        assert name["cell"] == "name"
        assert _width(name["box"]) <= NAME + 1, (
            f"{path} at {width} px: the name is {_width(name['box'])} px, wider than its {NAME}"
        )
    for width in WIDTHS:
        name = measured["/admin/leden", width]["heads"][0]
        assert abs(_width(name["box"]) - NAME) <= 1, (
            f"Leden at {width} px: the name is {_width(name['box'])} px where {NAME} fit"
        )
    # At 1 100 px Ontvangen has left: its room goes to the name, not behind Acties.
    for width in (1100, 1440):
        tight = measured["/admin/betalingen", width]["heads"]
        assert _width(tight[0]["box"]) < NAME - 1, (
            f"Betalingen at {width} px has room for the whole name"
        )
        assert abs(_width(tight[-1]["box"]) - ACTIONS) <= 1, (
            f"Betalingen at {width} px: the name left the actions "
            f"{_width(tight[-1]['box'])} px, not their {ACTIONS}"
        )


def test_the_white_space_falls_behind_the_last_column(measured):
    m = measured["/admin/leden", 1920]
    name, second, last = m["heads"][0], m["heads"][1], m["heads"][-1]
    assert abs(second["box"][0] - name["box"][1]) <= 1
    assert second["box"][0] <= m["frame"][0] + 1 + NAME + 1, (
        f"Leden at 1 920 px: the second head starts at {second['box'][0]}, "
        f"the frame at {m['frame'][0]} — white space between the first two columns"
    )
    others = sum(_width(h["box"]) for h in m["heads"][:-1])
    assert _width(last["box"]) > others, (
        f"Leden at 1 920 px: the last column is {_width(last['box'])} px, the others {others}"
    )


def test_a_column_head_never_wraps(measured):
    for (path, width), m in measured.items():
        for head in m["heads"]:
            where = f"{path} at {width} px, head '{head['cell']}'"
            assert head["height"] <= 37, f"{where} is {head['height']} px high — it wrapped"
            if _width(head["label"]) > 0:
                assert head["label"][1] <= head["box"][1] + 1, (
                    f"{where}: its label ends at {head['label'][1]}, the cell at {head['box'][1]}"
                )

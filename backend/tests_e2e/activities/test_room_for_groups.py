"""E2E: room for the groups (#1610; design-system-end-state §2.2, §3.3; CR-11 Q67).

Koen, 5 October 2026, on the activity's fiche in edit mode: the handles and the
white beside them cost a lot of room, the screen felt narrow, and a product no
longer stood on one line. Three things, all geometry, so all measured from the
rendered DOM:

- **one width** (#1929; Koen, 12 October 2026, to "Kies je c, één breedte van
  768 px voor elk record in beide modi?": "Ja"): the editor is the 768 px
  column with the summary card of 300 px at its right, as read mode is — the
  1 092 px editor of #1610 is gone; a field of full width fills the column, a
  text box included (#1635); with less than 964 px of frame (the Assistent's
  panel open) the summary is the band above the form (#1912);
- **denser rows**: a product's name · price · member price · maximum on one
  line, the settlement and "Publiek zichtbaar" on the second;
- **a narrower gutter**: 28 px for a composite item's handle, the child group
  12 px in at every width.

The activity is made for this file and removed again.

#1929, red first (13 October 2026): with the wide editor's rules out of the
stylesheet and this file as it stood, four tests were red — "assert 768 ==
1092" in the two width cases and in the save test, and "assert 662 > 900" on
the product's row. The save test proved only the width that came back and is
gone; the others measure 768 px now.

Broken on purpose (5 October 2026), each red for its own reason: the long-text rule of #1610
put back (#1635) → "Omschrijving is 768 px in a grid of 1 058"; the product's
first grid back on four tracks → the
maximum on a second line; the gutter back at 44 px; the child group's indent
back at 16 px. And for #1912 (12 October 2026), each locally and restored: the
a rule added that makes the figures the card's rows again (`display:grid`) →
"label and value are 278 px apart" at 1 440 px and with the panel open; a rule
added that gives every figure a third of the band → "label and value are 75 px
apart" (what Koen refused: "het label en het bedrag onnatuurlijk ver uit
elkaar").
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.activities.test_product_settlement import _db, _seed  # noqa: E402
from tests_e2e.schermen import (  # noqa: E402
    BASE,
    SUMMARY_SHAPE,
    assert_summary_band,
    login_met_sessie,
    pagina_klaar,
)

_M = """() => { const r = e => { if (!e) return null; const b = e.getBoundingClientRect(); return {x: Math.round(b.left), y: Math.round(b.top + scrollY), w: Math.round(b.width), h: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom + scrollY)}; };
  const q = s => document.querySelector(s);
  const product = q('[data-repeating-group^="p_order."] > [data-group-rows] > [data-group-row]');
  const comp = q('#aa-group-components > [data-group-rows] > [data-group-row]');
  const f = n => product ? r(product.querySelector(`[data-field$=".${n}"]`)) : null;
  const child = q('[data-repeating-group^="p_order."]');
  const own = (row, s) => row ? [...row.querySelectorAll(s)].find(e => e.closest('[data-group-row]') === row) : null;
  return {page: [document.documentElement.scrollWidth, innerWidth], length: document.documentElement.scrollHeight,
          mode: q('[data-form-flow]').dataset.mode,
          column: r(q('[data-form-column]')), summary: r(q('[data-summary-column]')),
          description: r(q('[data-field="description"]')), name_field: r(q('[data-field="name"]')),
          notes: r(q('[data-field="board_notes"]')), slug_field: r(q('[data-field="slug"]')),
          grid: r((q('[data-field="description"]') || document.body).closest('[data-form-grid]')),
          notes_grid: r((q('[data-field="board_notes"]') || document.body).closest('[data-form-grid]')),
          boxes: [r(q('[data-field="description"] textarea')), r(q('[data-field="board_notes"] textarea'))],
          facts: r(q('[data-activity-facts]')), inset: comp ? parseFloat(getComputedStyle(comp).paddingLeft) + parseFloat(getComputedStyle(comp).borderLeftWidth) : null,
          body: product ? r(product.querySelector('[data-row-body]')) : null,
          name: f('name'), price: f('price'), member: f('member_price'), max: f('max_participants'),
          settle: f('settlement'), active: f('is_active'),
          comp: r(comp), handle: r(own(comp, '[data-row-handle]')), title: r(own(comp, '[data-row-title-line]')),
          product_handle: r(own(product, '[data-row-handle]')), product_title: r(own(product, '[data-row-title-line]')), product_box: r(product),
          indent: child ? getComputedStyle(child).paddingLeft : null}; }"""


@pytest.fixture(scope="module")
def setup():
    from app.domains.activities import service
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity_id = _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), activity_id
        b.close()
    db = _db()
    try:
        service.delete_activity(db, activity_id, actor="e2e-1610@example.com")
    finally:
        db.close()


def _page(setup, width: int, edit: bool = True):
    b, session, activity_id = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    login_met_sessie(page, session)
    page.goto(f"/admin/activiteiten/{activity_id}" + ("?bewerken=1" if edit else ""))
    pagina_klaar(page)
    return page


@pytest.mark.parametrize("width", [1440, 1920])
def test_the_editor_keeps_the_record_width_and_the_summary_stands_beside_it(setup, width):
    """#1929: one width for every record, in both modes. The editor is the
    768 px column with the card of 300 px at its right, their tops level — at
    1 440 px (a frame of 1 168) as at 1 920 px (1 632). Red before: 1 092 px,
    and at 1 440 px the band above it."""
    page = _page(setup, width)
    try:
        m = page.evaluate(_M)
        shape = page.evaluate(SUMMARY_SHAPE)
        print("MEASURE room edit", width, m["column"], m["summary"], m["description"], m["body"])
        print("MEASURE summary shape edit", width, shape)
        assert m["mode"] == "edit" and m["column"]["w"] == 768
        assert m["summary"]["w"] == 300, f"the card is {m['summary']['w']} px wide"
        assert m["summary"]["x"] == m["column"]["right"] + 24, "the card stands at the form's right"
        assert m["summary"]["y"] == m["column"]["y"], "the card and the form start level"
        assert len({f["mid"] for f in shape["figures"]}) == len(shape["figures"]), (
            "beside the form every figure is a row of its own"
        )
        # #1635: a field of full width fills the column, a text box included —
        # Omschrijving and Interne nota from the left edge of Naam to the right
        # edge of Vriendelijke URL.
        print("MEASURE text boxes", width, m["description"], m["notes"], m["grid"], m["boxes"])
        for label, field, grid in (
            ("Omschrijving", m["description"], m["grid"]),
            ("Interne nota", m["notes"], m["notes_grid"]),
        ):
            assert field["w"] == grid["w"] > 700, (
                f"{label} is {field['w']} px in a grid of {grid['w']}"
            )
        assert m["description"]["x"] == m["name_field"]["x"]
        assert m["description"]["right"] == m["slug_field"]["right"]
        for box, field in zip(m["boxes"], (m["description"], m["notes"])):
            assert box["w"] == field["w"], (
                f"the text box is {box['w']} px in a field of {field['w']}"
            )
        assert m["name_field"]["w"] > 350
        assert m["page"][0] == width
        assert page.errors == []
    finally:
        page.close()

    read = _page(setup, width, edit=False)
    try:
        r = read.evaluate(_M)
        print("MEASURE room read", width, r["column"], r["summary"])
        assert r["mode"] == "read" and r["column"]["w"] == 768
        # #1635: nothing changes in read mode — the facts stay inside the 768 px
        # column (#1900: read mode shows facts, no field blocks).
        assert r["facts"] is not None and r["facts"]["w"] < 768
        assert r["facts"]["right"] <= r["column"]["right"]
        assert r["summary"]["x"] == r["column"]["right"] + 24 and r["summary"]["w"] == 300
        assert r["summary"]["y"] == r["column"]["y"], "#1587: the two cards start level"
    finally:
        read.close()


def _one_line(m: dict) -> None:
    fields = [m["name"], m["price"], m["member"], m["max"]]
    assert len({f["y"] for f in fields}) == 1, f"not on one line: {[f['y'] for f in fields]}"
    assert [f["x"] for f in fields] == sorted(f["x"] for f in fields), "out of order"
    assert m["name"]["w"] > m["price"]["w"] == m["member"]["w"] == m["max"]["w"], (
        "the name is the wide one"
    )
    assert m["max"]["right"] <= m["body"]["right"] + 1
    assert m["settle"]["y"] == m["active"]["y"] > m["name"]["y"], (
        "the choice and the switch share line two"
    )
    assert m["settle"]["x"] < m["active"]["x"]


def test_a_product_stands_on_one_line_and_its_choice_on_the_second(setup):
    """Red on master: the maximum stood on the second line, beside the settlement."""
    page = _page(setup, 1440)
    try:
        m = page.evaluate(_M)
        print(
            "MEASURE product row 1440",
            m["body"],
            [m[k]["w"] for k in ("name", "price", "member", "max")],
        )
        _one_line(m)
    finally:
        page.close()


def test_with_the_assistents_panel_open_the_panel_wins_and_the_row_still_fits(setup):
    """Less than 964 px of frame: the form is 768 px, the summary is the band
    above it (#1912: a strip of rows until then), and the product's four fields
    are still one line (the row has 649 px)."""
    page = _page(setup, 1440)
    try:
        page.get_by_role("button", name="Assistent").first.click()
        page.wait_for_function(
            "document.querySelector('[data-form-column]').getBoundingClientRect().width < 1000"
        )
        m = page.evaluate(_M)
        print("MEASURE panel open 1440", m["column"], m["summary"], m["body"])
        assert m["column"]["w"] == 768
        assert m["summary"]["bottom"] <= m["column"]["y"] and m["summary"]["w"] == 768
        shape = page.evaluate(SUMMARY_SHAPE)
        print("MEASURE summary shape panel open 1440", shape)
        assert_summary_band(shape, lines=2)
        _one_line(m)
        assert m["page"][0] == 1440
    finally:
        page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_the_gutter_is_28_px_and_the_child_list_stands_under_its_label(setup, width):
    """Red on master: a gutter of 44 px, and 16 px of indent on a desktop. Since
    #1900 a component is a card: its gutter starts inside the card's own edge
    (16 px of padding and the border), and its products are a list under their
    label, not indented behind a line."""
    page = _page(setup, width)
    try:
        m = page.evaluate(_M)
        print("MEASURE gutter", width, m["handle"], m["title"], m["indent"], m["body"], m["length"])
        assert m["inset"] == 17, f"a component is not a card: {m['inset']} px inside its edge"
        for box, handle, title, inset in (
            (m["comp"], m["handle"], m["title"], 17),
            (m["product_box"], m["product_handle"], m["product_title"], 0),
        ):
            assert title["x"] - box["x"] - inset == 28 + 8, (
                "the gutter is not 28 px (plus its 8 px gap)"
            )
            assert handle["w"] == 24 and handle["h"] == 44, handle
            assert box["x"] + inset <= handle["x"] and handle["right"] <= box["x"] + inset + 28, (
                "the handle leaves its gutter"
            )
        assert m["indent"] == "0px", "the products are indented behind a line again"
        assert m["page"][0] == width, "the page widened"
    finally:
        page.close()


def test_on_a_phone_nothing_widens_and_the_editor_is_shorter(setup):
    """The phone keeps its one column; the narrower gutter gives a product's row
    239 px where it had 207, and the editor lost a fifth of its length (it was
    about 6 000 px on HDEV for a fiche like this; the hint under every product
    went too)."""
    page = _page(setup, 390)
    try:
        m = page.evaluate(_M)
        print("MEASURE phone", m["column"], m["body"], m["length"])
        assert m["page"] == [390, 390]
        assert m["column"]["w"] == 358
        # The phone is as it was: the strip above the form, full width (#1912).
        assert (m["summary"]["x"], m["summary"]["w"]) == (m["column"]["x"], 358)
        assert m["summary"]["bottom"] <= m["column"]["y"]
        assert m["body"]["w"] >= 239
        # stacked: one field per line, in the order of the form
        ys = [m[k]["y"] for k in ("name", "price", "member", "max", "settle", "active")]
        assert ys == sorted(ys) and len(set(ys)) == 6
    finally:
        page.close()

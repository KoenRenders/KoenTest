"""E2E: room for the groups (#1610; design-system-end-state §2.2, §3.3; CR-11 Q67).

Koen, 5 October 2026, on the activity's fiche in edit mode: the handles and the
white beside them cost a lot of room, the screen felt narrow, and a product no
longer stood on one line. Three things, all geometry, so all measured from the
rendered DOM:

- **the wide column in edit mode**: a record with a composite group that is being
  edited takes the whole reading group — 1 380 px since CR-17 slice 4 (Koen, 9
  October 2026: "links houden, maar het scherm benutten"; the group was 1 092),
  with its summary above it as a strip; reading, saving and cancelling give
  the reading column and the card at the right again (844 px of frame at
  1 440, the 1 056 cap above); a field of full width fills the column, a text
  box included (#1635: #1610 kept long text at 768 px, with a gap at its
  right); below 1 380 px of frame the composite simply takes what the frame
  gives, summary beside her (the Assistent's panel: nothing changes);
- **denser rows**: a product's name · price · member price · maximum on one
  line, the settlement and "Publiek zichtbaar" on the second;
- **a narrower gutter**: 28 px for a composite item's handle, the child group
  12 px in at every width.

The activity is made for this file and removed again.

Broken on purpose (5 October 2026), each red for its own reason: the wide rule
taken out of the stylesheet → 768 in edit mode; the long-text rule of #1610
put back (#1635) → "Omschrijving is 768 px in a grid of 1 058"; the product's
first grid back on four tracks → the
maximum on a second line; the gutter back at 44 px; the child group's indent
back at 16 px.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402
from tests_e2e.test_product_settlement import _db, _seed  # noqa: E402

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
          grid: r(q('[data-field="description"]').closest('[data-form-grid]')),
          notes_grid: r(q('[data-field="board_notes"]').closest('[data-form-grid]')),
          boxes: [r(q('[data-field="description"] textarea')), r(q('[data-field="board_notes"] textarea'))],
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
def test_the_editor_takes_the_reading_group_and_the_summary_stands_above(setup, width):
    """Red on master: 768 px in both modes, the summary beside the form.

    Since CR-17 slice 4 the composite strip needs 1 380 px of frame: at
    1 920 the editor takes the whole reading group with her summary above;
    at 1 440 (1 168 px of frame) the composite takes what the frame gives
    and the summary stands beside her — the norm's own "with less than the
    frame, nothing changes".
    """
    page = _page(setup, width)
    try:
        m = page.evaluate(_M)
        print("MEASURE room edit", width, m["column"], m["summary"], m["description"], m["body"])
        assert m["mode"] == "edit"
        if width == 1920:
            assert m["column"]["w"] == 1380, "the editor does not take the whole reading group"
            assert (m["summary"]["x"], m["summary"]["w"]) == (m["column"]["x"], 1380)
            assert m["summary"]["bottom"] + 24 == m["column"]["y"], (
                "the strip is not 24 px above the form"
            )
            assert m["summary"]["h"] < 160, "above the form the summary is a strip, not the card"
        else:
            assert m["column"]["w"] == 844, "the composite column does not follow the frame"
            assert m["summary"]["x"] == m["column"]["right"] + 24 and m["summary"]["w"] == 300
        # #1635: a field of full width fills the column, a text box included —
        # Omschrijving and Interne nota from the left edge of Naam to the right
        # edge of Vriendelijke URL. Red on master: 768 px in a grid of 1 058.
        # Since CR-17 slice 4 the composite's whole group needs 1 380 px of
        # frame, so at 1 440 the grid fills the 844 px column (810 inside)
        # and at 1 920 the 1 380 px strip (1 346 inside).
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
        if width == 1920:
            assert m["name_field"]["w"] > 500
        else:
            # The reading column's own halves (the kit's 399 at this frame,
            # measured in test_form_fields too).
            assert m["name_field"]["w"] == 399
        assert m["page"][0] == width
        assert page.errors == []
    finally:
        page.close()

    read = _page(setup, width, edit=False)
    try:
        r = read.evaluate(_M)
        print("MEASURE room read", width, r["column"], r["summary"])
        assert r["mode"] == "read" and r["column"]["w"] == (844 if width == 1440 else 1056)
        # #1635: nothing changes in read mode — the value stays inside the
        # reading column, whatever she is at this width.
        assert r["description"]["w"] == r["grid"]["w"] < r["column"]["w"]
        assert r["summary"]["x"] == r["column"]["right"] + 24 and r["summary"]["w"] == 300
        assert r["summary"]["y"] == r["column"]["y"], "#1587: the two cards start level"
    finally:
        read.close()


def test_saving_and_cancelling_give_the_reading_column_back(setup):
    """The page is not loaded again: the form's answer replaces the form, and the
    layout follows what stands in it."""
    page = _page(setup, 1440)
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        assert page.evaluate(_M)["column"]["w"] == 844
        page.locator("[data-form-save]").click()
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        saved = page.evaluate(_M)
        assert saved["column"]["w"] == 844
        assert (
            saved["summary"]["x"] == saved["column"]["right"] + 24 and saved["summary"]["w"] == 300
        )
        assert saved["summary"]["y"] == saved["column"]["y"]
    finally:
        page.close()

    page = _page(setup, 1440)
    try:
        page.locator("[data-form-cancel]").click()
        pagina_klaar(page)
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        assert page.evaluate(_M)["column"]["w"] == 844
    finally:
        page.close()


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
    """Red on master: the maximum stood on the second line, beside the settlement.

    Since CR-17 slice 4 the composite strip needs 1 380 px of frame, so at
    1 440 the product's row is 725 px wide — and the four fields are still
    one line, with the settlement and the switch on the second.
    """
    page = _page(setup, 1440)
    try:
        m = page.evaluate(_M)
        print(
            "MEASURE product row 1440",
            m["body"],
            [m[k]["w"] for k in ("name", "price", "member", "max")],
        )
        _one_line(m)
        assert m["body"]["w"] > 700
    finally:
        page.close()


def test_with_the_assistents_panel_open_the_panel_wins_and_the_row_still_fits(setup):
    """Less than 1 092 px of frame: the form is 768 px, the strip stays above, and
    the product's four fields are still one line (the row has 649 px)."""
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
        _one_line(m)
        assert m["page"][0] == 1440
    finally:
        page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_the_gutter_is_28_px_and_the_child_group_12_px_in(setup, width):
    """Red on master: a gutter of 44 px, and 16 px of indent on a desktop."""
    page = _page(setup, width)
    try:
        m = page.evaluate(_M)
        print("MEASURE gutter", width, m["handle"], m["title"], m["indent"], m["body"], m["length"])
        for box, handle, title in (
            (m["comp"], m["handle"], m["title"]),
            (m["product_box"], m["product_handle"], m["product_title"]),
        ):
            assert title["x"] - box["x"] == 28 + 8, "the gutter is not 28 px (plus its 8 px gap)"
            assert handle["w"] == 24 and handle["h"] == 44, handle
            assert box["x"] <= handle["x"] and handle["right"] <= box["x"] + 28, (
                "the handle leaves its gutter"
            )
        assert m["indent"] == "12px"
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
        assert m["body"]["w"] >= 239
        # stacked: one field per line, in the order of the form
        ys = [m[k]["y"] for k in ("name", "price", "member", "max", "settle", "active")]
        assert ys == sorted(ys) and len(set(ys)) == 6
    finally:
        page.close()

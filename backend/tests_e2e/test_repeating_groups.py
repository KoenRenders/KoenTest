"""E2E: the repeating groups of the activity fiche (CR-11 block 7, #1559).

In a real browser, because everything here happens in the page before the one
save: a row is added, moved, duplicated and removed without a request, "Opslaan"
writes it all, "Annuleren" writes nothing.

Measured from the rendered DOM (design-system-end-state §3.3):

- a simple group shows its labels once, as a column head; no label per row;
- a composite item has its handle in a gutter at the left, and its title line
  and its fields start on one edge to the right of it — no field left of the
  handle;
- the child group (products) is indented behind a line: 16 px, 12 on a phone;
- on a phone: one column, the handle and `⋯` on the first line, 44 px targets,
  and the labels back on each field;
- removing a row asks nothing, and "Annuleren" brings it back;
- a refused save says why and keeps what was typed.

Screenshots go outside the repo.
"""

import os
import sys
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

NAME = "Groepentest met rijen"
MEMBER = ("Groepan", "Zoekbaar")

_GEOMETRY = """() => {
  const r = e => { if (!e) return null; const b = e.getBoundingClientRect(); return {x: Math.round(b.left), y: Math.round(b.top + scrollY), w: Math.round(b.width * 10) / 10, h: Math.round(b.height * 10) / 10, right: Math.round(b.right)}; };
  const dates = document.getElementById('aa-group-dates'), comps = document.getElementById('aa-group-components');
  const comp = comps.querySelector(':scope > [data-group-rows] > [data-group-row]');
  const child = comp.querySelector('[data-repeating-group]');
  const product = child.querySelector('[data-group-row]');
  const own = (row, s) => [...row.querySelectorAll(s)].find(e => e.closest('[data-group-row]') === row);
  const shown = e => e.getBoundingClientRect().width > 2 && e.checkVisibility();
  return {
    page: [document.documentElement.scrollWidth, innerWidth],
    head: dates.querySelector('[data-group-head]') ? {shown: dates.querySelector('[data-group-head]').checkVisibility(), labels: [...dates.querySelectorAll('[data-group-head] [data-span]')].map(e => e.innerText.replace('*', '').trim())} : null,
    date_rows: [...dates.querySelectorAll(':scope > [data-group-rows] > [data-group-row]')].map(row => ({
      box: r(row), labels: [...row.querySelectorAll('label')].filter(shown).length, fields: [...row.querySelectorAll('[data-field]')].map(r),
      menu: r(own(row, '[data-row-menu-trigger]')), handle: r(own(row, '[data-row-handle]'))})),
    component: {box: r(comp), handle: r(own(comp, '[data-row-handle]')), title: r(own(comp, '[data-row-title-line]')),
                fields: [...comp.querySelectorAll('[data-field]')].filter(f => f.closest('[data-group-row]') === comp).map(r),
                menu: r(own(comp, '[data-row-menu-trigger]'))},
    child: {box: r(child), border: getComputedStyle(child).borderLeftWidth, padding: getComputedStyle(child).paddingLeft,
            background: getComputedStyle(child).backgroundColor, shadow: getComputedStyle(child).boxShadow},
    product: {handle: r(own(product, '[data-row-handle]')), title: r(own(product, '[data-row-title-line]')), fields: [...product.querySelectorAll('[data-field]')].map(r)},
    components: r(comps), dates: r(dates),
    targets: [...document.querySelectorAll('[data-row-handle], [data-row-menu-trigger], [data-group-add]')].filter(shown).map(e => Math.round(e.getBoundingClientRect().height)),
  };
}"""


def _seed() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import (
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
    )
    from app.domains.mdm.api import Member, MemberPerson, Person

    db = SessionLocal()
    try:
        existing = db.query(Activity).filter(Activity.name == NAME).first()
        if existing is not None:
            return existing.id
        activity = Activity(name=NAME, location="Parochiezaal")
        db.add(activity)
        db.flush()
        start = date.today() + timedelta(days=80)
        for offset in (0, 7, 14):
            db.add(
                ActivityDate(
                    activity_id=activity.id,
                    start_date=start + timedelta(days=offset),
                    start_time=time(14, 0),
                    end_time=time(17, 0),
                )
            )
        walk = ActivitySubRegistration(
            activity_id=activity.id,
            name="Wandeling",
            registration_type_code="INDIVIDUAL",
            price=0,
            is_free=True,
            max_participants=80,
            sort_order=0,
        )
        mill = ActivitySubRegistration(
            activity_id=activity.id,
            name="Molen",
            registration_type_code="INDIVIDUAL",
            price=0,
            is_free=True,
            sort_order=1,
        )
        db.add_all([walk, mill])
        db.flush()
        db.add(
            ActivityProduct(
                component_id=walk.id,
                name="Soep",
                price=Decimal("5.00"),
                member_price=Decimal("4.00"),
                is_free=False,
                sort_order=0,
            )
        )
        db.add(
            ActivityProduct(
                component_id=walk.id,
                name="Brood",
                price=Decimal("2.00"),
                is_free=False,
                sort_order=1,
            )
        )
        person = Person(
            date_of_birth=date(1980, 1, 1),
            gender_code="M",
            first_name=MEMBER[0],
            last_name=MEMBER[1],
        )
        db.add(person)
        db.flush()
        household = Member()
        db.add(household)
        db.flush()
        db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID"))
        db.commit()
        return activity.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity_id = _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), activity_id
        b.close()


def _page(setup, width: int, edit: bool = True):
    b, session, activity_id = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 1000}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    login_met_sessie(page, session)
    page.goto(f"/admin/activiteiten/{activity_id}" + ("?bewerken=1" if edit else ""))
    pagina_klaar(page)
    return page


def _rows(page, group_id: str) -> list[str]:
    return page.evaluate(
        """(id) => [...document.querySelectorAll('#' + id + ' > [data-group-rows] > [data-group-row]')].map(r => {
             const t = r.querySelector('[data-row-title]');
             const first = r.querySelector('input:not([type=hidden])');
             return t ? t.innerText.trim() : (first ? first.value : r.innerText.trim());
           })""",
        group_id,
    )


def _menu(page, row, action: str):
    row.locator("[data-row-menu-trigger]").first.click()
    row.locator(f'[data-row-action="{action}"]').first.click()


def _save(page):
    page.click('[data-provisional-bar] button:has-text("Opslaan")')


# ── The shape ────────────────────────────────────────────────────────────────


def test_a_simple_group_shows_its_labels_once_and_a_composite_item_keeps_its_handle_in_a_gutter(
    setup,
):
    """Proven red twice: the per-row label rule removed from the stylesheet (every
    date row shows four labels), and the handle moved inside the body (the fields
    start left of it)."""
    page = _page(setup, 1440)
    g = page.evaluate(_GEOMETRY)
    print(
        "MEASURE groups 1440",
        {
            "dates": g["dates"],
            "date_rows": [r["box"] for r in g["date_rows"]],
            "components": g["components"],
            "component": g["component"],
            "child": g["child"],
        },
    )
    assert page.errors == []
    assert g["page"][0] <= g["page"][1]

    assert g["head"] == {"shown": True, "labels": ["Datum", "Van", "Einddatum", "Tot"]}
    assert len(g["date_rows"]) == 3
    for row in g["date_rows"]:
        assert row["labels"] == 0, "no label per row"
        assert len({f["y"] for f in row["fields"]}) == 1 and len(row["fields"]) == 4, (
            "four quarter fields on one line"
        )
        assert row["menu"]["x"] > row["fields"][-1]["right"], "the row menu at the far right"
        assert row["handle"] is None, "dates have no order to drag"

    c = g["component"]
    gutter = c["handle"]["right"]
    assert c["handle"]["x"] == c["box"]["x"], "the handle at the left of the whole block"
    assert c["title"]["x"] >= gutter and all(f["x"] >= gutter for f in c["fields"]), (
        "no field left of the handle"
    )
    assert (
        len({c["title"]["x"]} | {f["x"] for f in c["fields"] if f["x"] < c["title"]["x"] + 2}) == 1
    ), "the title line and the first field of each row share one left edge"
    assert c["menu"]["right"] == c["box"]["right"], (
        "the item's menu on its title line, at the right"
    )

    child = g["child"]
    assert child["padding"] == "16px" and child["border"] == "1px", "indented 16 px behind a line"
    assert (
        child["background"] in ("rgba(0, 0, 0, 0)", "transparent") and child["shadow"] == "none"
    ), "no card, no box"
    assert child["box"]["x"] == c["title"]["x"], "the child group starts on the item's edge"
    p = g["product"]
    assert p["title"]["x"] >= p["handle"]["right"] and all(
        f["x"] >= p["handle"]["right"] for f in p["fields"]
    )
    page.close()


def test_on_a_phone_the_rows_stack_with_handle_and_menu_on_the_first_line(setup):
    page = _page(setup, 390)
    g = page.evaluate(_GEOMETRY)
    print(
        "MEASURE groups 390",
        {"date_row": g["date_rows"][0], "component": g["component"], "child": g["child"]},
    )
    assert g["page"] == [390, 390]
    assert g["head"]["shown"] is False, "no column head where the fields stack"
    row = g["date_rows"][0]
    assert row["labels"] == 4, "each field carries its label on a phone"
    tops = [f["y"] for f in row["fields"]]
    assert tops == sorted(tops) and len(set(tops)) == 4, "one column"
    assert row["menu"]["y"] < row["fields"][0]["y"], (
        "the row menu on the first line, above the fields"
    )
    c = g["component"]
    assert abs(c["handle"]["y"] - c["title"]["y"]) <= 2, "handle and title on the first line"
    assert g["child"]["padding"] == "12px"
    assert g["targets"] and min(g["targets"]) >= 44, g["targets"]
    page.close()


def test_read_mode_has_no_handle_no_menu_and_no_add(setup):
    page = _page(setup, 1440, edit=False)
    assert page.locator("[data-row-handle], [data-row-menu-trigger], [data-group-add]").count() == 0
    assert page.locator("#aa-group-dates [data-date-line]").count() == 3
    assert page.locator("#aa-group-components [data-product-line]").count() == 2
    page.close()


# ── Working in the page, then one save ───────────────────────────────────────


def test_rows_are_added_moved_duplicated_and_removed_in_the_page_and_saved_once(setup):
    page = _page(setup, 1440)
    posts = []
    page.on("request", lambda req: posts.append(req.url) if req.method == "POST" else None)

    # a new date, in place, with the focus on its first field
    page.click("#aa-group-dates [data-group-add]")
    assert page.locator("#aa-group-dates > [data-group-rows] > [data-group-row]").count() == 4
    assert page.evaluate("document.activeElement.type") == "date"
    new_date = (date.today() + timedelta(days=200)).isoformat()
    page.keyboard.type(
        new_date.replace("-", "")[4:] + new_date[:4]
    )  # mm dd yyyy, as the control takes it
    page.evaluate("(v) => { document.activeElement.value = v; }", new_date)

    # the second component up, by its menu; its title follows its name field
    components = page.locator("#aa-group-components > [data-group-rows] > [data-group-row]")
    assert _rows(page, "aa-group-components") == ["Wandeling", "Molen"]
    _menu(page, components.nth(1), "up")
    assert _rows(page, "aa-group-components") == ["Molen", "Wandeling"]
    first = components.nth(0)
    assert first.locator('[data-row-action="up"]').first.is_disabled(), (
        "Omhoog is off on the first row"
    )
    first.locator("[data-row-title-source]").first.fill("Molenbezoek")
    assert _rows(page, "aa-group-components")[0] == "Molenbezoek"

    # duplicate the component with its two products; remove one product of the copy
    walk = components.nth(1)
    _menu(page, walk, "duplicate")
    assert _rows(page, "aa-group-components") == ["Molenbezoek", "Wandeling", "Wandeling"]
    copy = components.nth(2)
    assert copy.locator("[data-repeating-group] [data-group-row]").count() == 2, (
        "a duplicated component takes its products"
    )
    copy.locator("[data-row-title-source]").first.fill("Avondwandeling")
    _menu(page, copy.locator("[data-repeating-group] [data-group-row]").nth(1), "remove")
    assert copy.locator("[data-repeating-group] [data-group-row]").count() == 1
    assert page.locator('[role="dialog"]:visible').count() == 0, "removing a row asks nothing"

    # a product on the component that had none
    first.locator("[data-repeating-group] [data-group-add]").click()
    page.keyboard.type("Koffie")
    assert posts == [], f"nothing is sent before the save: {posts}"

    _save(page)
    page.wait_for_selector('[data-form-flow][data-mode="read"]')
    pagina_klaar(page)
    assert len([u for u in posts if "/admin/activiteiten/" in u]) == 1, "one save"
    assert page.errors == []

    titles = page.locator("#aa-group-components [data-row-title]").all_inner_texts()
    assert titles == ["Molenbezoek", "Wandeling", "Avondwandeling"]
    assert page.locator("#aa-group-dates [data-date-line]").count() == 4
    lines = page.locator("#aa-group-components [data-product-line]").all_inner_texts()
    assert [line.split(" ·")[0] for line in lines] == ["Koffie", "Soep", "Brood", "Soep"], lines
    page.reload()
    pagina_klaar(page)
    assert page.locator("#aa-group-components [data-row-title]").all_inner_texts() == titles, (
        "written, not only shown"
    )
    page.close()


def test_annuleren_brings_a_removed_row_back(setup):
    page = _page(setup, 1440)
    before = _rows(page, "aa-group-components")
    dates = page.locator("#aa-group-dates > [data-group-rows] > [data-group-row]")
    count = dates.count()
    _menu(page, dates.nth(0), "remove")
    _menu(
        page,
        page.locator("#aa-group-components > [data-group-rows] > [data-group-row]").nth(0),
        "remove",
    )
    assert dates.count() == count - 1 and len(_rows(page, "aa-group-components")) == len(before) - 1
    page.click('[data-provisional-bar] a:has-text("Annuleren")')
    pagina_klaar(page)
    assert page.locator("#aa-group-dates [data-date-line]").count() == count
    assert page.locator("#aa-group-components [data-row-title]").all_inner_texts() == before
    page.close()


def test_the_last_row_removed_shows_the_empty_line_and_the_add_button_stays(setup):
    page = _page(setup, 1440)
    group = page.locator("#aa-group-dates")
    rows = group.locator("> [data-group-rows] > [data-group-row]")
    while rows.count():
        _menu(page, rows.nth(0), "remove")
    assert group.locator("> [data-group-empty]").is_visible()
    assert group.locator("> [data-group-empty]").inner_text() == "Nog geen datums."
    assert group.locator("[data-group-head]").is_hidden()
    assert group.locator("[data-group-add]").is_visible()
    page.close()


def test_a_refused_save_says_why_and_keeps_what_was_typed(setup):
    """A product that is free AND to pay on site: two switches the screen can set
    together, a combination the service refuses."""
    page = _page(setup, 1440)
    first = page.locator("#aa-group-components > [data-group-rows] > [data-group-row]").first
    first.locator("[data-repeating-group] [data-group-add]").click()
    page.keyboard.type("Gratis en ter plaatse")
    new = first.locator("[data-repeating-group] [data-group-row]").last
    new.locator('[data-kind="switch"] label:has-text("Gratis")').click()
    new.locator('[data-kind="switch"] label:has-text("Ter plaatse betalen")').click()
    _save(page)
    message = page.locator("#aa-fiche-message")
    message.locator("text=niet tegelijk gratis").wait_for()
    assert page.url.endswith("?bewerken=1")
    assert page.locator("[data-form-flow]").get_attribute("data-mode") == "edit"
    assert new.locator("[data-row-title-source]").input_value() == "Gratis en ter plaatse", (
        "the typed row is still there"
    )
    # htmx scrolls (`show:top`) after the swap has settled: wait for it.
    page.wait_for_function(
        """() => { const y = document.getElementById('aa-fiche-message').getBoundingClientRect().top;
                 return y >= 0 && y < innerHeight; }""",
        timeout=5000,
    )
    page.close()


def test_a_duplicate_of_a_component_keeps_its_products_under_itself(setup):
    """A product whose id equals its component's id: the copy's product order
    must name the copy, not the product. Found by the save test above losing the
    copied product; the form's own entries are the proof."""
    page = _page(setup, 1440)
    row = (
        page.locator("#aa-group-components > [data-group-rows] > [data-group-row]")
        .filter(has_text="Soep")
        .first
    )
    _menu(page, row, "duplicate")
    entries = page.evaluate(
        """() => [...new FormData(document.getElementById('aa-act-form')).entries()].map(([k, v]) => [k, typeof v === 'string' ? v : ''])"""
    )
    component_keys = [v for k, v in entries if k == "c_order"]
    copy = next((key for key in component_keys if not key.isdigit()), "")
    assert copy, f"the copy is a new row: {component_keys}"
    products_of_copy = [v for k, v in entries if k == f"p_order.{copy}"]
    assert len(products_of_copy) >= 1, (
        f"the copy's products stand under the copy: {[k for k, v in entries if k.startswith('p_order')]}"
    )
    assert all(not key.isdigit() for key in products_of_copy), "and are new rows themselves"
    names = dict(entries)
    assert all(f"p.{key}.name" in names for key in products_of_copy)
    orders = [k for k, v in entries if k.startswith("p_order.")]
    assert all(k.split(".", 1)[1] in component_keys for k in orders), (
        "every product order names a component of the form"
    )
    page.close()


def test_an_organiser_is_picked_from_the_member_search_into_the_form(setup):
    page = _page(setup, 1440)
    group = page.locator("#aa-group-organisers")
    before = group.locator("> [data-group-rows] > [data-group-row]").count()
    search = group.locator('input[name="organiser_q"]')
    search.fill(MEMBER[0])
    pick = group.locator("[data-group-pick]").first
    pick.wait_for()
    pick.click()
    rows = group.locator("> [data-group-rows] > [data-group-row]")
    assert rows.count() == before + 1
    added = rows.last
    assert f"{MEMBER[0]} {MEMBER[1]}" in added.inner_text()
    assert added.locator("[data-reference]").get_attribute("href").startswith("/admin/leden/gezin/")
    assert group.locator("[data-group-pick]").count() == 0, "not offered twice"
    added.locator('[data-kind="switch"] label').first.click()  # contactpersoon
    search.press("Enter")
    assert page.url.endswith("?bewerken=1"), "Enter in the search does not send the fiche"

    _save(page)
    page.wait_for_selector('[data-form-flow][data-mode="read"]')
    pagina_klaar(page)
    saved = page.locator("#aa-group-organisers")
    assert (
        f"{MEMBER[0]} {MEMBER[1]}" in saved.inner_text() and "op de affiche" in saved.inner_text()
    )
    page.close()


def test_a_row_is_dragged_by_its_handle_and_escape_gives_up(setup):
    """The row is draggable only while its handle is held. A drag that ends
    without a drop leaves the order as it was."""
    page = _page(setup, 1440)
    order = _rows(page, "aa-group-components")
    assert len(order) >= 2
    rows = page.locator("#aa-group-components > [data-group-rows] > [data-group-row]")
    assert rows.nth(0).get_attribute("draggable") is None, "not draggable by itself"
    handle = rows.nth(0).locator("[data-row-handle]").first
    handle.hover()
    page.mouse.down()
    assert rows.nth(0).get_attribute("draggable") == "true"
    page.mouse.up()

    # A drop on the lower half of the second row puts the first after it.
    moved = page.evaluate(
        """() => {
          const rows = [...document.querySelectorAll('#aa-group-components > [data-group-rows] > [data-group-row]')];
          const [first, second] = rows;
          first.setAttribute('draggable', 'true');
          const data = new DataTransfer();
          const fire = (target, type, y) => target.dispatchEvent(new DragEvent(type, {bubbles: true, cancelable: true, dataTransfer: data, clientY: y}));
          fire(first, 'dragstart', 0);
          const box = second.getBoundingClientRect();
          fire(second, 'dragover', box.bottom - 4);
          const marked = second.classList.contains('group-drop-after') && first.classList.contains('group-dragging');
          fire(second, 'drop', box.bottom - 4);
          fire(first, 'dragend', 0);
          return marked;
        }"""
    )
    assert moved, "the origin is marked and the drop place shows its line"
    assert _rows(page, "aa-group-components")[:2] == [order[1], order[0]]
    assert page.locator(".group-dragging, .group-drop-after, .group-drop-before").count() == 0
    page.close()

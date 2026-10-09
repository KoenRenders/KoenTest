"""E2E: Personen in the browser (CR-22 S7, #1712; R18, R25).

- the screen opens on "Zonder gezin", in the admin shell with "Personen"
  marked in the menu, at 1440 and at 390 px no wider than the window, every
  row's `⋯` on one line down the right edge;
- typing in the search cuts the list without replacing the field, and the
  count in the toolbar follows;
- **Verwijderen behind `⋯` asks first** — the in-app confirmation, with the
  person's name — and after "Bevestigen" the row is gone and the count on the
  view is one lower; cancelling leaves the person there.

The test makes its own person without a household and deletes him.

On master there is no route `/admin/personen`.
"""

import os
import sys
import uuid

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, login_als_admin, pagina_klaar  # noqa: E402

PAGE = "/admin/personen"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _board(browser, width: int, height: int):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    login_als_admin(page, email, make_session_value(email))
    return page


@pytest.fixture
def loose_person():
    """A person in no household, with an e-mail address; gone again afterwards
    when the test did not delete him."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import ContactDetail, Person
    from app.soft_delete import soft_delete

    tag = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        person = Person(first_name="Proef", last_name=f"Persoon-{tag}")
        db.add(person)
        db.flush()
        db.add(
            ContactDetail(
                person_id=person.id,
                contact_type_code="EMAIL",
                value=f"proef-{tag}@example.org",
                is_primary=True,
            )
        )
        db.commit()
        made = {"id": person.id, "name": f"Proef Persoon-{tag}", "tag": tag}
    finally:
        db.close()
    yield made
    db = SessionLocal()
    try:
        left = db.query(Person).filter(Person.id == made["id"]).first()
        if left is not None:
            for contact in left.contact_details:
                soft_delete(contact)
            soft_delete(left)
            db.commit()
    finally:
        db.close()


SHAPE = """() => { const q = s => document.querySelector(s), all = s => [...document.querySelectorAll(s)];
  const marked = all('nav a[aria-current="page"]').map(a => a.getAttribute('href'));
  return {title: q('h1').innerText.trim(), marked,
          view: (q('input[name=zicht]:checked') || {}).value,
          rows: all('tr[data-row]').length,
          menus: [...new Set(all('[data-row-menu-trigger]').map(e => Math.round(e.getBoundingClientRect().right)))],
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (390, 844)])
def test_the_screen_opens_on_zonder_gezin_in_the_shell(browser, loose_person, width, height):
    page = _board(browser, width, height)
    page.goto(PAGE)
    pagina_klaar(page)
    shape = page.evaluate(SHAPE)
    print("MEASURE persons", width, shape)
    assert shape["title"] == "Personen" and shape["view"] == "zonder", shape
    assert PAGE in shape["marked"], "Personen is not the marked menu item"
    assert shape["rows"] >= 1 and len(shape["menus"]) == 1, "the rows' menus do not line up"
    assert shape["page"][0] == shape["page"][1], "wider than the window"
    expect(page.locator(f'tr[data-person="{loose_person["id"]}"]')).to_contain_text(
        loose_person["name"]
    )
    page.close()


def test_searching_cuts_the_list_and_deleting_asks_first(browser, loose_person):
    page = _board(browser, 1440, 900)
    page.goto(PAGE)
    pagina_klaar(page)
    row = page.locator(f'tr[data-person="{loose_person["id"]}"]')
    search = page.locator('#personen-filter input[type="search"]')
    with htmx_afgerond(page):
        search.press_sequentially(loose_person["tag"], delay=30)
    expect(page.locator("tr[data-row]")).to_have_count(1)
    expect(row).to_be_visible()
    assert search.input_value() == loose_person["tag"], "the search field was replaced"
    expect(page.locator("#personen-filter-count")).to_have_text("1–1 van 1")
    expect(page.locator("#personen-filter-n-zonder")).to_have_text("(1)")

    # Cancelling leaves the person there.
    row.locator("[data-row-menu-trigger]").click()
    item = row.get_by_role("menuitem", name="Verwijderen")
    assert item.get_attribute("data-confirm") == f"{loose_person['name']} verwijderen?"
    item.click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text(f"{loose_person['name']} verwijderen?")
    dialog.get_by_role("button", name="Annuleren").click()
    expect(dialog).to_be_hidden()
    expect(row).to_be_visible()

    # Confirming deletes him: the row goes, the counts follow.
    row.locator("[data-row-menu-trigger]").click()
    row.get_by_role("menuitem", name="Verwijderen").click()
    with htmx_afgerond(page):
        page.get_by_role("button", name="Bevestigen").click()
    expect(row).to_have_count(0)
    expect(page.locator("#personen-filter-count")).to_have_text("0–0 van 0")
    expect(page.locator("#personen-filter-n-zonder")).to_have_text("(0)")
    expect(page.locator("#personen-lijst")).to_contain_text("Geen personen gevonden")
    page.close()

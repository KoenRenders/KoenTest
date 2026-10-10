"""E2E #1854 — the address fields of the back office on a phone.

The address grid (street, house number and bus on one row; the postal code
under it — the fixed decision) shared its width in quarters at every width. On
a phone a quarter of the card is 68 px and the label "Huisnummer *" is 94 px:
its text ran into "Bus", stood on two lines, and pushed the house number field
20 px below the bus field. In the household's card the title "Adres bewerken"
stood on two lines beside the buttons.

Held here, from the rendered page, on the two screens that show the grid — the
new household and a household's address card in its edit state:

- at 390 px: both labels on one line and apart, the two fields on one line, the
  bus to the right of the house number, the street still the widest field, no
  sideways scroll; in the card the title on one line;
- on a desktop: the three columns as they were — the house number and the bus
  equally wide, the street twice as wide.

Proven red (locally, restored): the grid's narrow columns taken out again
(`grid-cols-4` alone) → both screens fail at 390 px on "the label Huisnummer
stands on 2 lines"; the wrap taken off the card's title row → the card fails on
"the title is 40 px high".
"""

from __future__ import annotations

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

RUN = secrets.token_hex(3)

_GRID = """() => {
  const r = e => e.getBoundingClientRect();
  const text = label => { const g = document.createRange(); g.selectNodeContents(label); return g; };
  const lines = label => new Set([...text(label).getClientRects()].map(c => Math.round(c.top))).size;
  const field = id => document.getElementById(id);
  const label = id => document.querySelector(`label[for="${id}"]`);
  const street = field('street'), house = field('house_number'), bus = field('bus_number');
  const title = [...document.querySelectorAll('#adres-kaart span')]
    .find(e => e.textContent.trim() === 'Adres bewerken' && e.checkVisibility());
  return {
    house_lines: lines(label('house_number')), bus_lines: lines(label('bus_number')),
    gap: text(label('bus_number')).getBoundingClientRect().left
         - text(label('house_number')).getBoundingClientRect().right,
    tops: [r(street).top, r(house).top, r(bus).top].map(Math.round),
    widths: [r(street).width, r(house).width, r(bus).width].map(Math.round),
    bus_right_of_house: r(bus).left >= r(house).right,
    postal_code_below: r(field('postal_code')).top >= r(bus).bottom,
    title_height: title ? Math.round(r(title).height) : null,
    sideways: document.documentElement.scrollWidth - window.innerWidth,
  };
}"""


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import csrf_token_for, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    session = make_session_value(email)
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        login_met_sessie(page, session)
        page.csrf = csrf_token_for(session)  # type: ignore[attr-defined]
        yield page
        browser.close()


@pytest.fixture(scope="module")
def household(page) -> int:
    """A household made through the door the screen uses; its id."""
    page.goto("/admin/leden/nieuw")
    pagina_klaar(page)
    postal_code = page.eval_on_selector(
        "#postal_code", "el => [...el.options].map(o => o.value).filter(Boolean)[0]"
    )
    form = {
        "street": "Voorbeeldstraat",
        "house_number": "128",
        "bus_number": "3B",
        "postal_code": postal_code,
        "m0_first_name": "Hanne",
        "m0_last_name": f"Adres-{RUN}",
        "m0_date_of_birth": "1980-03-04",
        "m0_gender_code": "F",
        "m0_email": f"adres-{RUN}@example.com",
        "m0_phone": "",
        "m0_mobile": "0470 00 00 01",
    }
    answer = page.request.post(
        "/admin/leden", form=form, headers={"X-CSRF-Token": page.csrf, "HX-Request": "true"}
    )
    assert answer.status == 204, (answer.status, answer.text()[:300])
    return int(answer.headers["hx-redirect"].rsplit("/", 1)[-1])


def _new_household_screen(page, _household) -> None:
    page.goto("/admin/leden/nieuw")
    pagina_klaar(page)


def _address_card(page, household) -> None:
    page.goto(f"/admin/leden/gezin/{household}")
    pagina_klaar(page)
    page.locator("#adres-kaart").get_by_role("button", name="Bewerken").click()
    page.locator("#house_number").wait_for(state="visible")


SCREENS = {"the new household": _new_household_screen, "the address card": _address_card}


@pytest.mark.parametrize("screen", SCREENS)
def test_the_address_row_reads_on_a_phone(page, household, screen):
    page.set_viewport_size({"width": 390, "height": 844})
    SCREENS[screen](page, household)

    seen = page.evaluate(_GRID)

    assert seen["house_lines"] == 1, f"the label Huisnummer stands on {seen['house_lines']} lines"
    assert seen["bus_lines"] == 1
    assert seen["gap"] >= 8, f"the labels Huisnummer and Bus are {seen['gap']} px apart"
    street, house, bus = seen["tops"]
    assert street == house == bus, f"the three fields do not stand on one line: {seen['tops']}"
    assert seen["bus_right_of_house"], "the bus is not to the right of the house number"
    assert seen["postal_code_below"], "the postal code is not on a row of its own"
    assert seen["widths"][0] > seen["widths"][1] > seen["widths"][2] >= 60, (
        f"street, house number, bus are {seen['widths']} px wide"
    )
    assert seen["sideways"] <= 0, f"the page scrolls sideways by {seen['sideways']} px"
    if screen == "the address card":
        assert seen["title_height"] is not None, "the card's title was not found — still looking?"
        assert seen["title_height"] <= 24, f"the title is {seen['title_height']} px high"


@pytest.mark.parametrize("screen", SCREENS)
def test_on_a_desktop_the_columns_are_as_they_were(page, household, screen):
    page.set_viewport_size({"width": 1100, "height": 844})
    SCREENS[screen](page, household)

    seen = page.evaluate(_GRID)

    street, house, bus = seen["widths"]
    assert house == bus, f"house number and bus are {house} and {bus} px wide"
    assert abs(street - (2 * house + 12)) <= 1, f"the street is {street} px, a quarter is {house}"
    assert len(set(seen["tops"])) == 1 and seen["house_lines"] == 1
    assert seen["sideways"] <= 0

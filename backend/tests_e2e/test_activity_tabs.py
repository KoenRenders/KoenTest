"""E2E: the activity's summary and its list tabs in a browser (#1560, CR-11
pilot A, K6).

What a server test cannot see:

- **the frame does not move** (B7 test 12): the head and the tab bar stand at
  the same place on Gegevens, Inschrijvingen and Betalingen;
- **the summary card** is 300 px wide at the right of the form on a desktop and
  a strip under the tabs on a phone; a list tab has neither, its toolbar stands
  directly under the tabs and its table takes the full width;
- **one open row per list**: a second row closes the first; a collapsed group
  hides its rows and shows them again as they were;
- **the way back lands on the row**: from the registration's page the tab opens
  with that row unfolded and the focus on it;
- **the copy button** copies the public link in place — a check mark at the
  button, no screen, no toast — and when the browser refuses, shows no check
  mark and selects the address;
- on the embedded Betalingen tab a click on a row unfolds it and leaves the
  page where it is, and the row's own action stays a button of its own.

The activity is the seeded one the payments list names. Nothing is changed.

Proven red (each on this branch, restored after):
- the list's one `openRow` state made a state per row → the one-open-row test
  fails (two rows open);
- the group's collapse rule taken out of the CSS → the group test fails;
- the landing on the open row taken out of the shell's handler after a
  navigation → the way-back test fails (the focus is on the title);
- the card's container query removed → the desktop geometry test fails (the
  card is a strip of the full width);
- the toggle's click area removed → the click-on-the-date test fails.
"""

import os
import re
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402

_BOXES = """() => {
  const box = s => { const e = document.querySelector(s); if (!e || !e.checkVisibility()) return null;
    const r = e.getBoundingClientRect(); return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)}; };
  const rows = [...document.querySelectorAll('tr[data-row]')].filter(e => e.checkVisibility());
  const r0 = rows.length ? rows[0].getBoundingClientRect() : null;
  return {
    head: box('[data-record-head]'), tabs: box('[data-related-tabs]'),
    card: box('[data-summary-card]'), form: box('[data-form-column]'),
    toolbar: box('[data-toolbar]'), frame: box('[data-table-frame]'),
    first_row: r0 ? {y: Math.round(r0.top), bottom: Math.round(r0.bottom)} : null,
    scroll: document.documentElement.scrollWidth, width: innerWidth, height: innerHeight,
  };
}"""

_OPEN = """() => [...document.querySelectorAll('tr[data-row-detail]')]
  .filter(e => e.checkVisibility()).map(e => e.id.replace('row-detail-', ''))"""


def _expect_open(page, keys: list) -> None:
    """The unfolded rows are exactly `keys` — waited for, because Alpine shows
    and hides a row a tick after the click."""
    try:
        page.wait_for_function(
            f"keys => JSON.stringify(({_OPEN})()) === JSON.stringify(keys)", arg=keys, timeout=5000
        )
    except Exception:
        raise AssertionError(f"open rows {page.evaluate(_OPEN)}, expected {keys}") from None


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _page(browser, size, **context):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(
        base_url=BASE, viewport={"width": size[0], "height": size[1]}, **context
    )
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    return page


@pytest.fixture(scope="module")
def activity(browser) -> str:
    """The address of the seeded activity that has registrations and bookings:
    the one the payments list names under Context."""
    page = _page(browser, (1440, 900))
    page.goto("/admin/betalingen")
    pagina_klaar(page)
    found = re.search(
        r"/admin/activiteiten/(\d+)\?terug=", page.locator("#betalingen-lijst").inner_html()
    )
    page.close()
    assert found, "the seeded payments list names no activity"
    return f"/admin/activiteiten/{found.group(1)}"


def _boxes(page, url) -> dict:
    page.goto(url)
    pagina_klaar(page)
    return page.evaluate(_BOXES)


def test_the_frame_does_not_move_and_only_gegevens_has_the_card(browser, activity):
    page = _page(browser, (1440, 1080))
    gegevens = _boxes(page, activity)
    registrations = _boxes(page, activity + "/inschrijvingen")
    payments = _boxes(page, activity + "/betalingen")
    page.close()

    for tab in (registrations, payments):
        assert tab["head"] == gegevens["head"] and tab["tabs"] == gegevens["tabs"], (gegevens, tab)
        assert tab["scroll"] == tab["width"], tab
    # Gegevens: the card, 300 px, at the right of the form and level with it.
    card, form = gegevens["card"], gegevens["form"]
    assert card and card["w"] == 300, gegevens
    assert card["x"] >= form["x"] + form["w"] and card["y"] == form["y"], gegevens
    assert 190 <= card["h"] <= 240, card
    # A list tab: no card, the toolbar directly under the tabs, the table as
    # wide as the tab bar, and the first row well inside the first screen.
    under_tabs = gegevens["tabs"]["y"] + gegevens["tabs"]["h"]
    for tab in (registrations, payments):
        assert tab["card"] is None, tab
        assert 0 <= tab["toolbar"]["y"] - under_tabs <= 16, tab
        assert tab["frame"]["w"] == tab["tabs"]["w"], tab
        assert tab["first_row"]["y"] - under_tabs <= 150, tab


def test_on_a_phone_the_summary_is_a_strip_under_the_tabs(browser, activity):
    page = _page(browser, (390, 844))
    gegevens = _boxes(page, activity)
    registrations = _boxes(page, activity + "/inschrijvingen")
    payments = _boxes(page, activity + "/betalingen")
    page.close()

    card, form, tabs = gegevens["card"], gegevens["form"], gegevens["tabs"]
    assert card["w"] == 358 and 110 <= card["h"] <= 150, card
    # Under the tabs, above the form.
    assert tabs["y"] + tabs["h"] <= card["y"] and card["y"] + card["h"] <= form["y"], gegevens
    for name, tab in (("inschrijvingen", registrations), ("betalingen", payments)):
        assert tab["card"] is None and tab["scroll"] == 390, (name, tab)
        # The first row is on the first screen, whole.
        assert tab["first_row"]["bottom"] <= tab["height"], (name, tab)


def test_one_row_is_open_at_a_time_and_a_group_keeps_what_was_open(browser, activity):
    page = _page(browser, (1440, 1080))
    page.goto(activity + "/inschrijvingen")
    pagina_klaar(page)
    toggles = page.locator("[data-row-toggle]")
    assert toggles.count() >= 2, "the seeded activity needs two registrations"
    first, second = (toggles.nth(i).get_attribute("data-row-toggle") for i in (0, 1))
    _expect_open(page, [])

    toggles.nth(0).click()
    _expect_open(page, [first])
    assert toggles.nth(0).get_attribute("aria-expanded") == "true"
    # The unfolded row: its parts side by side, and nothing that edits.
    detail = page.locator(f"#row-detail-{first}")
    tops = detail.locator("[data-row-part]").evaluate_all(
        "els => els.map(e => Math.round(e.getBoundingClientRect().top))"
    )
    assert len(tops) == 4 and len(set(tops)) == 1, tops
    assert detail.locator("button, form, input").count() == 0
    assert detail.get_by_role("link", name="Inschrijving openen").count() == 1

    # A click anywhere on another row — its date — opens that one and closes the first.
    # (`force`: the toggle's click area lies over the cell, which is the point.)
    page.locator("tr[data-row]").nth(1).locator('[data-cell="date"]').click(force=True)
    _expect_open(page, [second])
    assert toggles.nth(0).get_attribute("aria-expanded") == "false"

    # The group collapses: its rows and the open one are hidden; open again, the
    # same row is still unfolded.
    group = page.locator("[data-group-toggle]").first
    group.click()
    assert group.get_attribute("aria-expanded") == "false"
    _expect_open(page, [])
    assert page.locator("tr[data-row]").first.is_hidden()
    group.click()
    _expect_open(page, [second])

    # The same toggle again closes the row.
    toggles.nth(1).click()
    _expect_open(page, [])
    page.close()


def test_the_way_back_from_a_registration_lands_on_its_row(browser, activity):
    page = _page(browser, (1440, 1080))
    page.goto(activity + "/inschrijvingen?sort=-naam")
    pagina_klaar(page)
    toggle = page.locator("[data-row-toggle]").nth(1)
    key = toggle.get_attribute("data-row-toggle")
    toggle.click()
    page.locator(f"#row-detail-{key}").get_by_role("link", name="Inschrijving openen").click()
    pagina_klaar(page)
    assert f"/admin/inschrijvingen/{key}" in page.url

    page.locator(f"a[href*='/inschrijvingen?'][href*='rij={key}']").first.click()
    pagina_klaar(page)
    assert page.url.endswith(f"/inschrijvingen?sort=-naam&rij={key}"), page.url
    _expect_open(page, [key])
    page.wait_for_function(
        "() => document.activeElement && document.activeElement.dataset.rowToggle"
    )
    assert page.evaluate("() => document.activeElement.dataset.rowToggle") == key
    page.close()


def test_the_toolbar_keeps_its_state_in_the_tabs_address(browser, activity):
    page = _page(browser, (1440, 1080))
    page.goto(activity + "/inschrijvingen")
    pagina_klaar(page)
    names = [n.strip() for n in page.locator("[data-row-toggle]").all_inner_texts()]
    # The second name: the seeded registrations share an e-mail address that
    # holds the first one's name, and the search reads the address too.
    needle = names[1].split()[0]
    page.locator('#reg-filter input[type="search"]').fill(needle)
    page.wait_for_function("() => location.search.includes('q=')")
    htmx_stil(page)
    assert "/inschrijvingen?" in page.url and "/lijst" not in page.url
    shown = [n.strip() for n in page.locator("[data-row-toggle]").all_inner_texts()]
    assert shown == [names[1]], shown
    assert page.locator("[data-toolbar-count]").inner_text().strip() == "1–1 van 1"
    # One shell and one record head: the fragment landed in the list holder.
    assert page.locator("[data-record-head]").count() == 1
    page.close()


def test_the_copy_button_copies_in_place(browser, activity):
    page = _page(browser, (1440, 1080), permissions=["clipboard-read", "clipboard-write"])
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    page.goto(activity)
    pagina_klaar(page)
    card = page.locator("[data-summary-card]")
    link = card.locator("[data-summary-link]").get_attribute("href")
    button = card.locator("button[data-copy]")
    icons = button.locator("span")
    assert icons.nth(0).is_visible() and icons.nth(1).is_hidden()
    before = page.url

    button.click()
    icons.nth(1).wait_for(state="visible")
    # The check mark stands where the copy icon stood; nothing else happened.
    assert icons.nth(0).is_hidden()
    assert page.evaluate("() => navigator.clipboard.readText()") == link
    assert page.url == before and not dialogs
    assert page.locator("#toasts > *").count() == 0
    assert page.locator("[role=dialog]:visible").count() == 0
    page.close()


def test_a_refused_copy_shows_no_check_mark_and_selects_the_address(browser, activity):
    page = _page(browser, (1440, 1080))
    page.goto(activity)
    pagina_klaar(page)
    # The browser refuses both ways of copying.
    page.evaluate(
        """() => { Object.defineProperty(navigator, 'clipboard', {value: {writeText: () => Promise.reject(new Error('refused'))}, configurable: true});
                   document.execCommand = () => false; }"""
    )
    card = page.locator("[data-summary-card]")
    button = card.locator("button[data-copy]")
    button.click()
    page.wait_for_function("() => String(getSelection()).length > 0")
    assert button.locator("span").nth(1).is_hidden(), "a check mark after a copy that failed"
    selected = page.evaluate("() => String(getSelection())")
    assert selected == card.locator("[data-summary-link]").inner_text()
    page.close()


def test_an_embedded_booking_unfolds_and_its_action_stays_its_own(browser, activity):
    page = _page(browser, (1440, 1080))
    page.goto(activity + "/betalingen")
    pagina_klaar(page)
    before = page.url
    row = page.locator("tr[data-row]").first
    key = row.locator("[data-row-toggle]").get_attribute("data-row-toggle")
    # A click on the amount unfolds the row; the page stays.
    row.locator("[data-amount]").click(force=True)
    _expect_open(page, [key])
    assert page.url == before
    detail = page.locator(f"#row-detail-{key}")
    assert detail.locator("[data-row-part]").count() == 2
    # The row's ⋯ opens its menu and does not fold the row.
    row.locator("[data-row-menu-trigger]").click()
    row.locator("[data-row-menu]").wait_for(state="visible")
    _expect_open(page, [key])
    page.keyboard.press("Escape")

    # "Betaling openen" → the booking's page → back on the tab, the row open.
    detail.get_by_role("link", name="Betaling openen").click()
    pagina_klaar(page)
    assert f"/admin/betalingen/{key}" in page.url
    page.locator("[data-way-back]").click()
    pagina_klaar(page)
    assert page.url.endswith(f"/betalingen?boeking={key}"), page.url
    _expect_open(page, [key])
    page.close()

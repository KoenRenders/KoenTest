"""E2E: the public shell in a browser (#1588, CR-11 pilot B, P1).

What a server test cannot see:

- **the header's heights**: 64 px on a phone, 112 px at 768 (two rows), 80 px at
  1 440; it sticks at y 0 while the environment banner above it scrolls away;
- **one container**: 358 / 720 / 1 248 px for the header, the content and the
  footer — the header's and the footer's left edge are the same at 1 440;
- **the drawer** on a phone: 360 px, OVER the page (the content does not move),
  a real close button where the menu button was; Escape and the backdrop close
  it and the focus returns to the menu button; while it is open the focus stays
  inside and the page behind it is inert;
- **the account menu** on a desktop opens under the first name and closes on
  Escape;
- **the footer**: one row of columns at 1 440, stacked on a phone, the legal
  line under it, 88 px kept free for the bell; nothing scrolls sideways.

Nothing is changed in the database.

Proven red (each on this branch, restored after):
- the header's tablet rule removed from the CSS → the heights test fails (64 at
  768);
- `position: sticky` taken off the header → the sticky test fails;
- the drawer made a block in the flow → the drawer test fails (the content
  moves);
- `:inert` taken off `<main>` → the focus test fails;
- the footer's padding for the bell removed → the footer test fails.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

_BOXES = """() => {
  const box = e => { if (!e || !e.checkVisibility()) return null; const r = e.getBoundingClientRect();
    return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), r: Math.round(r.right), b: Math.round(r.bottom)}; };
  const q = s => document.querySelector(s);
  const doc = y => y === null ? null : y + Math.round(scrollY);
  const legal = box(q('[data-footer-line]')), core = box(q('.site-footer-core'));
  return {
    banner: box(q('[data-env-banner]')), header: box(q('.site-header')), grid: box(q('.site-header-grid')),
    pages: box(q('#site-nav-breed')), account: box(q('[data-site-account]')), menu: box(q('[data-menu-button]')),
    drawer: box(q('#site-nav-mobiel')), close: box(q('[data-menu-close]')), backdrop: box(q('.site-drawer-backdrop')),
    main: box(q('#main')), core: core, row: box(q('[data-footer-row]')), legal: legal,
    free_under_legal: legal && core ? core.b - legal.b : null,
    columns: [...document.querySelectorAll('[data-footer-row] > section')].map(s => Math.round(s.getBoundingClientRect().left)),
    bell: box(q('[data-raakje-bell]')),
    scroll: document.documentElement.scrollWidth, width: innerWidth, height: innerHeight,
  };
}"""

_TWO_FRAMES = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _home(browser, size, signed_in=False):
    page = browser.new_page(base_url=BASE, viewport={"width": size[0], "height": size[1]})
    if signed_in:
        from app.domains.auth.api import make_session_value
        from tests.conftest import SEEDED_ADMIN_EMAIL

        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    page.goto("/")
    pagina_klaar(page)
    return page


@pytest.mark.parametrize(
    "size, height, container",
    [((390, 844), 64, 358), ((768, 900), 112, 720), ((1440, 900), 80, 1248)],
)
def test_the_header_has_its_height_and_one_container_holds_everything(
    browser, size, height, container
):
    page = _home(browser, size)
    m = page.evaluate(_BOXES)
    page.close()
    assert m["header"]["h"] == height and m["header"]["w"] == size[0], m
    # Header, content and footer on the same container: the same left edge and
    # the same width — the footer no longer sticks out.
    for part in ("grid", "main", "core"):
        assert m[part]["w"] == container and m[part]["x"] == m["grid"]["x"], (part, m)
    if size[0] == 390:
        assert m["menu"]["w"] == 44 and m["menu"]["h"] == 44 and m["pages"] is None, m
    else:
        assert m["menu"] is None and m["pages"] and m["account"], m
        # The links and the account stand inside the band.
        assert m["pages"]["b"] <= m["header"]["b"] and m["account"]["b"] <= m["header"]["b"], m
    assert m["scroll"] == size[0], m


def test_the_header_sticks_at_the_top_and_the_banner_scrolls_away(browser):
    page = _home(browser, (390, 844))
    before = page.evaluate(_BOXES)
    if before["banner"] is None:
        page.close()
        pytest.skip("no environment banner in this environment")
    # In the flow: the banner first, the header under it.
    assert before["banner"]["y"] == 0 and before["header"]["y"] == before["banner"]["h"], before
    page.evaluate("() => window.scrollTo(0, 300)")
    page.evaluate(_TWO_FRAMES)
    after = page.evaluate(_BOXES)
    page.close()
    assert after["header"]["y"] == 0, "the header does not stick at the top"
    assert after["banner"] is None or after["banner"]["b"] <= 0, "the banner stayed on the screen"


def test_the_drawer_lies_over_the_page_and_closes_three_ways(browser):
    page = _home(browser, (390, 844), signed_in=True)
    closed = page.evaluate(_BOXES)
    assert closed["drawer"] is None and closed["backdrop"] is None
    button = page.locator("[data-menu-button]")
    button.click()
    drawer = page.locator("#site-nav-mobiel")
    drawer.wait_for(state="visible")
    m = page.evaluate(_BOXES)
    # 360 px at the right, full height, over the page: the content did not move.
    assert (m["drawer"]["w"], m["drawer"]["r"], m["drawer"]["y"], m["drawer"]["h"]) == (
        360,
        390,
        0,
        844,
    ), m
    assert m["main"]["x"] == closed["main"]["x"] and m["main"]["w"] == closed["main"]["w"], m
    assert m["backdrop"]["w"] == 390, m
    # The close button where the menu button was (the same right edge), 44 px.
    assert m["close"]["w"] == 44 and abs(m["close"]["r"] - closed["menu"]["r"]) <= 1, m
    # Rows of 48 px; the account's items under the pages.
    heights = drawer.locator(".site-drawer-row").evaluate_all(
        "els => els.map(e => Math.round(e.getBoundingClientRect().height))"
    )
    assert heights and min(heights) >= 48, heights
    assert drawer.locator("[data-account-item]").count() >= 2
    # The focus went to the close button.
    assert page.evaluate("() => document.activeElement.hasAttribute('data-menu-close')")

    # Escape closes, and the focus is back on the menu button.
    page.keyboard.press("Escape")
    drawer.wait_for(state="hidden")
    page.wait_for_function("() => document.activeElement.hasAttribute('data-menu-button')")
    # The backdrop closes.
    button.click()
    drawer.wait_for(state="visible")
    page.mouse.click(10, 400)
    drawer.wait_for(state="hidden")
    # The close button closes.
    button.click()
    drawer.wait_for(state="visible")
    page.locator("[data-menu-close]").click()
    drawer.wait_for(state="hidden")
    page.wait_for_function("() => document.activeElement.hasAttribute('data-menu-button')")
    page.close()


def test_with_the_drawer_open_the_focus_stays_inside_and_the_page_is_inert(browser):
    page = _home(browser, (390, 844), signed_in=True)
    page.locator("[data-menu-button]").click()
    page.locator("#site-nav-mobiel").wait_for(state="visible")
    state = page.evaluate(
        """() => ({main: document.querySelector('#main').inert, header: document.querySelector('.site-header').inert,
                   footer: document.querySelector('.site-footer').inert})"""
    )
    assert state == {"main": True, "header": True, "footer": True}, state
    # A full round of Tab never leaves the drawer for the page behind it.
    focusable = page.locator("#site-nav-mobiel a, #site-nav-mobiel button").count()
    outside = []
    for _ in range(focusable + 3):
        page.keyboard.press("Tab")
        where = page.evaluate(
            """() => { const a = document.activeElement; if (!a || a === document.body) return 'chrome';
                       return a.closest('#site-nav-mobiel') ? 'drawer' : (a.id || a.tagName); }"""
        )
        if where not in ("drawer", "chrome"):
            outside.append(where)
    assert not outside, f"the focus left the drawer: {outside}"
    # Closed again, the page is usable.
    page.keyboard.press("Escape")
    page.locator("#site-nav-mobiel").wait_for(state="hidden")
    assert page.evaluate("() => document.querySelector('#main').inert") is False
    page.close()


def test_the_first_name_opens_the_account_menu(browser):
    page = _home(browser, (1440, 900), signed_in=True)
    button = page.locator("[data-account-button]")
    menu = page.locator("[data-account-menu]")
    assert menu.is_hidden()
    button.click()
    menu.wait_for(state="visible")
    box, band = menu.bounding_box(), page.evaluate(_BOXES)["header"]
    # Under the band, inside the window.
    assert box["y"] >= band["b"] - 20 and box["x"] + box["width"] <= 1440, box
    items = menu.locator("[data-account-item]").evaluate_all(
        "els => els.map(e => e.dataset.accountItem)"
    )
    assert items[-1] == "sign-out" and "admin" in items, items
    page.keyboard.press("Escape")
    menu.wait_for(state="hidden")
    assert page.evaluate("() => document.activeElement.hasAttribute('data-account-button')")
    page.close()


def test_the_footer_is_one_row_on_a_desktop_and_keeps_room_for_the_bell(browser):
    wide = _home(browser, (1440, 900))
    w = wide.evaluate(_BOXES)
    wide.close()
    phone = _home(browser, (390, 844))
    p = phone.evaluate(_BOXES)
    phone.close()
    # The columns stand side by side on a desktop and under each other on a
    # phone (the seed may have one column only: then both are one).
    assert len(set(w["columns"])) == len(w["columns"]), w
    assert len(set(p["columns"])) <= 1, p
    for m in (w, p):
        assert m["legal"]["y"] >= (m["row"]["b"] if m["row"] else m["core"]["y"]), m
        if m["bell"] is not None:
            # 88 px free under the legal line: the bell (56 px, 16 px from the
            # bottom) never lies over it at the end of the page.
            assert m["free_under_legal"] >= 88, m
        assert m["scroll"] == m["width"], m
    assert p["legal"]["x"] == 16, p

"""E2E: the account shell "Mijn <site>" (CR-22 S3, #1706; R14, Q16, Q35, Q38;
C6 T14).

- on a phone (390 px) the DRAWER's account menu is the navigation: it reaches
  the landing page and Mijn gezin, each item with its own icon; the page itself
  shows no menu, and the links at its bottom reach the other pages;
- on a desktop the account menu stands on the left of the page, 240 px wide,
  the content beside it, and the item of the open page is marked;
- the title may wrap, it is never cut off, and the page is no wider than the
  window.

Geometry, so read from the rendered page (the seeded member).

On master `d45633ff` there is no route `/mijn`, and the account menu holds one
member item, "Mijn gezin", drawn with the house (`_site_account.html:18`).
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _member(browser, width: int, height: int):
    from app.domains.auth.api import make_session_value
    from seed_e2e import MARKER_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    login_met_sessie(page, make_session_value(MARKER_EMAIL), BASE)
    return page


ITEMS = """(scope) => [...document.querySelectorAll(scope + ' [data-account-item="member"]')].map(a => ({
  href: a.getAttribute('href'), text: a.textContent.trim(), h: Math.round(a.getBoundingClientRect().height),
  icon: a.querySelector('svg') ? a.querySelector('svg').innerHTML.length : 0, shown: a.checkVisibility()}))"""
PAGE = """() => { const q = s => document.querySelector(s), r = e => e.getBoundingClientRect();
  const menu = q('[data-account-page-menu]'), content = q('[data-account-content]'), title = q('#main h1');
  const links = q('[data-account-links]');
  return {menu: menu.checkVisibility() ? [Math.round(r(menu).left), Math.round(r(menu).width)] : null,
          content: [Math.round(r(content).left), Math.round(r(content).width)], main: Math.round(r(q('#main')).left),
          title: [title.textContent.trim(), title.scrollWidth <= title.clientWidth + 1, getComputedStyle(title).textOverflow],
          current: [...document.querySelectorAll('[data-account-page-menu] a[aria-current="page"]')].map(a => a.getAttribute('href')),
          rows: [...document.querySelectorAll('[data-account-page-menu] a')].map(a => Math.round(r(a).height)),
          links: links && links.checkVisibility() ? [...links.querySelectorAll('a')].map(a => [a.getAttribute('href'), Math.round(r(a).height)]) : null,
          card: !!q('#main [data-membership-status]'),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


def test_on_a_phone_the_drawers_account_menu_reaches_every_page(browser):
    page = _member(browser, 390, 844)
    page.goto("/")
    pagina_klaar(page)
    page.locator("[data-menu-button]").click()
    page.locator("#site-nav-mobiel").wait_for(state="visible")
    items = page.evaluate(ITEMS, "[data-drawer-account]")
    print("MEASURE drawer account items", items)
    assert [i["href"] for i in items] == [
        "/mijn",
        "/mijn/gegevens",
        "/leden/gezin",
        "/mijn/inschrijvingen",
    ], items
    assert items[0]["text"].startswith("Mijn ")
    assert [i["text"] for i in items[1:]] == ["Mijn gegevens", "Mijn gezin", "Mijn inschrijvingen"]
    assert all(i["shown"] and i["h"] >= 44 for i in items), items
    # One glyph per meaning: the two items do not draw the same icon.
    assert all(i["icon"] for i in items) and len({i["icon"] for i in items}) == 4, items
    for href in ("/mijn", "/mijn/gegevens", "/leden/gezin", "/mijn/inschrijvingen"):
        page.goto("/")
        pagina_klaar(page)
        page.locator("[data-menu-button]").click()
        page.locator(f'[data-drawer-account] a[href="{href}"]').click()
        page.wait_for_url(f"**{href}")
        pagina_klaar(page)
        assert page.locator("#main h1").first.is_visible()
        assert not page.locator("#site-nav-mobiel").is_visible(), "the drawer stayed open"
    page.close()


def test_on_a_phone_the_page_shows_no_menu_and_links_at_its_bottom(browser):
    page = _member(browser, 390, 844)
    page.goto("/mijn")
    pagina_klaar(page)
    m = page.evaluate(PAGE)
    print("MEASURE account page 390", m)
    assert m["menu"] is None, "the page shows a menu of its own on a phone"
    assert m["content"] == [16, 358] and m["card"], m
    assert m["title"][0].startswith("Mijn ") and m["title"][1] and m["title"][2] != "ellipsis", m[
        "title"
    ]
    assert m["links"] and [href for href, _h in m["links"]] == [
        "/mijn/gegevens",
        "/leden/gezin",
        "/mijn/inschrijvingen",
    ], m["links"]
    assert all(h >= 44 for _href, h in m["links"]), m["links"]
    assert m["page"][0] == m["page"][1]
    page.locator('[data-account-links] a[href="/leden/gezin"]').click()
    page.wait_for_url("**/leden/gezin")
    page.close()


@pytest.mark.parametrize("width", [1440, 768])
def test_on_a_desktop_the_menu_stands_left_of_the_content(browser, width):
    page = _member(browser, width, 900)
    page.goto("/mijn")
    pagina_klaar(page)
    m = page.evaluate(PAGE)
    print("MEASURE account page", width, m)
    assert m["menu"] == [m["main"], 240], m
    # 32 px between the menu and the content, which takes the rest — at most
    # 768 px, the width of the public form page (the card is as wide as on Mijn gezin).
    assert m["content"][0] == m["main"] + 240 + 32, m
    rest = width - 2 * m["main"] - 240 - 32
    assert m["content"][1] == min(768, rest), f"the content is {m['content'][1]} px of {rest}"
    assert m["current"] == ["/mijn"] and len(m["rows"]) == 4 and min(m["rows"]) >= 44, m
    assert m["links"] is None, "the bottom links show on a desktop"
    assert m["card"] and m["title"][1]
    assert m["page"][0] == m["page"][1]
    page.close()

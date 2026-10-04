"""E2E: the admin frame at its widths, and the public site untouched (CR-11 block 1, #1482).

Measured from the DOM (design-system-end-state §1.4):

- 1 920 px: the sidebar 224 px, the top bar 64 px, the page margin 32 px, a list
  page as wide as the frame allows;
- 1 440 px: the sidebar 224 px, the margin 24 px;
- 1 280 px: the rail, 64 px, the labels gone and each item named by its title;
- 390 px: no sidebar until the menu button, then the drawer; the account button
  and the assistant's icon in the top bar; no horizontal scroll;
- the user's choice survives a reload: collapsed at 1 920 stays 64 px, expanded
  at 1 280 stays 224 px.

The public site keeps its tokens: the computed styles of the home page are the
values they had before this block (the full pixel comparison is the screenshot
set's manifest, which stays out of the repo).

Screenshots go outside the repo.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1482"
LIST = "/admin/betalingen"

_FRAME = """() => {
  const r = s => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return {x: Math.round(b.x), right: Math.round(b.right), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height), shown: e.checkVisibility()}; };
  const main = document.querySelector('#main');
  const label = document.querySelector('#admin-nav-zijbalk .nav-label');
  return {page: [document.documentElement.scrollWidth, innerWidth],
          sidebar: r('#admin-zijbalk'), topbar: r('header.sticky'), content: r('.admin-content'),
          account: r('[data-account]'), assistant: r('[data-assistant]'), menu: r('header button[aria-controls=admin-zijbalk]'),
          gutter: Math.round(parseFloat(getComputedStyle(main).paddingLeft)),
          label_shown: label ? label.checkVisibility() : null,
          rail: document.documentElement.classList.contains('nav-rail')};
}"""


@pytest.fixture(scope="module")
def browser_and_session():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _page(browser_and_session, width: int, path: str = LIST):
    b, session = browser_and_session
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    page.goto(path)
    pagina_klaar(page)
    return page


def _shot(page, name: str) -> None:
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/{name}.png")


@pytest.mark.parametrize("width,nav,gutter", [(1920, 224, 32), (1440, 224, 24)])
def test_wide_the_sidebar_is_224_and_a_list_takes_the_width(
    browser_and_session, width, nav, gutter
):
    page = _page(browser_and_session, width)
    m = page.evaluate(_FRAME)
    print("MEASURE", width, m)
    _shot(page, f"{width}-lijst")
    page.close()

    assert m["sidebar"]["w"] == nav and m["sidebar"]["shown"], m
    assert m["topbar"]["h"] == 64, m
    assert m["gutter"] == gutter, m
    assert m["content"]["x"] == nav + gutter, "the list starts at the margin beside the sidebar"
    assert m["content"]["w"] == width - nav - 2 * gutter, (
        "a list page is as wide as the frame allows"
    )
    assert m["label_shown"], "the labels show beside the icons"


def test_at_1280_the_sidebar_is_a_rail(browser_and_session):
    page = _page(browser_and_session, 1280)
    m = page.evaluate(_FRAME)
    titles = page.evaluate(
        "() => [...document.querySelectorAll('#admin-nav-zijbalk a')].map(a => a.title)"
    )
    print("MEASURE 1280", m)
    _shot(page, "1280-rail")
    page.close()

    assert m["rail"] and m["sidebar"]["w"] == 64, m
    assert not m["label_shown"], "a rail shows icons, not labels"
    assert all(titles), "every rail item is named by its tooltip"


def test_at_390_a_drawer_and_the_account_in_the_bar(browser_and_session):
    page = _page(browser_and_session, 390)
    closed = page.evaluate(_FRAME)
    page.locator("header button[aria-controls=admin-zijbalk]").click()
    page.locator("#admin-zijbalk").wait_for(state="visible")
    opened = page.evaluate(_FRAME)
    _shot(page, "390-lade")
    print("MEASURE 390", closed, opened)
    page.close()

    assert closed["page"][0] == closed["page"][1], f"no horizontal scroll: {closed}"
    assert not closed["sidebar"]["shown"], "no sidebar on a phone until the menu button"
    assert closed["menu"]["shown"] and closed["topbar"]["h"] == 64, closed
    assert closed["account"]["shown"] and closed["account"]["right"] <= 390, (
        "the account button stays in the bar"
    )
    assert closed["assistant"]["shown"] and closed["assistant"]["w"] <= 48, (
        "the assistant's icon alone"
    )
    assert opened["sidebar"]["shown"] and opened["sidebar"]["w"] == 312, opened
    assert opened["label_shown"], "the drawer shows the labels"


@pytest.mark.parametrize("width,before,after", [(1920, 224, 64), (1280, 64, 224)])
def test_the_choice_survives_a_reload(browser_and_session, width, before, after):
    page = _page(browser_and_session, width)
    page.evaluate("() => localStorage.removeItem('raak-admin-sidebar')")
    page.reload()
    pagina_klaar(page)
    first = page.evaluate(_FRAME)["sidebar"]["w"]
    page.locator("[data-nav-toggle]").click()
    page.reload()
    pagina_klaar(page)
    second = page.evaluate(_FRAME)["sidebar"]["w"]
    page.evaluate("() => localStorage.removeItem('raak-admin-sidebar')")
    page.close()

    assert (first, second) == (before, after)


def test_warning_is_the_real_orange_on_payments(browser_and_session):
    """Block 3's correction (Koen, 2 October 2026): warning is 194 65 12 —
    the Openstaand badge and an open amount. Contrast measured at the build:
    5.18:1 on white, 4.52:1 on the badge's soft orange."""
    page = _page(browser_and_session, 1440)
    colours = page.evaluate(
        """() => ({
      badge: [...document.querySelectorAll('span')].filter(s => s.textContent.trim() === 'Openstaand').map(s => getComputedStyle(s).color),
      open_amount: [...document.querySelectorAll('[data-balance] span')].filter(e => e.className.includes && e.className.includes('text-brand-warning')).map(e => getComputedStyle(e).color),
    })"""
    )
    print("MEASURE warning", colours)
    page.close()

    assert colours["badge"] and set(colours["badge"]) == {"rgb(194, 65, 12)"}, colours
    assert colours["open_amount"] and set(colours["open_amount"]) == {"rgb(194, 65, 12)"}, colours


def test_the_public_site_keeps_its_tokens(browser_and_session):
    """The home page's own values: the admin's palette, radius and face did not
    reach the site. They are master's: the screenshot set of all 26 public
    screens is byte-identical before (b5a80a38) and after this block."""
    b, _session = browser_and_session
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.goto("/")
    pagina_klaar(page)
    s = page.evaluate(
        """() => {
      const cs = (sel, p) => { const e = document.querySelector(sel); return e ? getComputedStyle(e)[p] : null; };
      return {body: cs('body', 'backgroundColor'), header: cs('header > nav', 'backgroundColor'),
              font: cs('body', 'fontFamily'), ink: cs('main', 'color')};
    }"""
    )
    print("MEASURE public", s)
    page.close()

    assert s == {
        "body": "rgb(244, 246, 250)",
        "header": "rgb(36, 75, 197)",
        "font": "Inter, system-ui, sans-serif",
        "ink": "rgb(25, 38, 56)",
    }, s

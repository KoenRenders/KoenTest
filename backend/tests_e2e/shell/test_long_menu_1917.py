"""E2E: the public header with a long menu (#1917).

Measured on master before the repair (the issue, 12 October 2026, 1 440 px):
the header was one grid row from 1 200 px — brand `minmax(0,1fr)`, pages,
account — so each page added to the menu took its width from the logo: 192 px
with five pages added, 15 px with seven, gone with eight, and the page
scrolled sideways from eleven.

Koen, 15 October 2026, "a": the menu wraps to a second row, and a third if it
must, CSS only. Koen, 16 October 2026, "5a": the account stays fixed at the
top right, and the menu keeps room for it on every row.

The walk: the seed's short menu at 768, 1 100, 1 200 and 1 440 px gives the
header of before (112 px up to 1 199, 80 from 1 200). Fourteen pages and a
section of #2024 added: the logo keeps the width it has with the short menu,
no link stands under the account or outside the window, the page does not
scroll sideways — signed out and signed in (the account's room differs).
`MEASURE` lines print the rows; set `E2E_PRINTS` to keep a print of each.

Broken on purpose (16 October 2026): `flex-wrap:wrap` taken off the header's
row → the long menu pushes the page sideways and the test is red; the
`padding-right` of the account's room taken out → with the short menu a link
stands under the account at 1 200 px and that test is red. (With the header's
wrap taken off, the long menu squeezed beside the logo and wrapped there; the
assertion that it stands UNDER the logo is what turns that red.) After the
review of #2067: the brand given 4 px of padding → the logo is no longer where
master put it and the short-menu test is red; the account's `max-width` taken
off and the room cut to 14rem → the forty-character name overlaps the menu;
`overflow:hidden` on the header → the section's list on a later row is
clipped and that test is red. (With the `max-width` in place a smaller room
only cuts the name shorter: the room and the account's width are one variable.)
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

WIDTHS = (768, 1100, 1200, 1440)

MEASURE = """() => {
  const box = (el) => { const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height),
            right: Math.round(r.right), bottom: Math.round(r.bottom)}; };
  const header = document.querySelector('header.site-header');
  const account = document.querySelector('[data-site-account]');
  const logo = document.querySelector('[data-site-brand]');
  const links = [...document.querySelectorAll('#site-nav-breed > a, #site-nav-breed [data-menu-section]')]
    .map(box);
  return {header: box(header), account: box(account), logo: box(logo),
          logo_img: logo.querySelector('img, span') ? box(logo.querySelector('img, span')) : null,
          links, rows: [...new Set(links.map(l => l.y))].length,
          scroll: document.documentElement.scrollWidth, window: window.innerWidth};
}"""


def _overlap(a: dict, b: dict) -> bool:
    return (
        a["x"] < b["right"]
        and b["x"] < a["right"]
        and a["y"] < b["bottom"]
        and b["y"] < a["bottom"]
    )


@pytest.fixture(scope="module")
def long_menu():
    """Fourteen pages of thirteen characters and a section with two pages, as
    the issue measured; removed again afterwards."""
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.cms.api import CmsPage, publish, update_page
    from app.domains.cms.service import create_page
    from app.schemas.cms import CmsPageCreate, CmsPageUpdate

    tag = secrets.token_hex(3)
    db = SessionLocal()
    made: list[int] = []
    try:
        for i in range(14):
            page = create_page(
                db,
                CmsPageCreate(
                    title=f"Pagina nr {i:02d}x", slug=f"lang-{tag}-{i}", sort_order=8000 + i
                ),
            )
            publish(db, page.id)
            made.append(page.id)
        section = create_page(
            db, CmsPageCreate(title="Over ons", slug=f"sectie-{tag}", sort_order=8100)
        )
        publish(db, section.id)
        for i in range(2):
            child = create_page(db, CmsPageCreate(title=f"Onder {i}", slug=f"onder-{tag}-{i}"))
            publish(db, child.id)
            update_page(db, child.id, CmsPageUpdate(parent_id=section.id))
            made.insert(0, child.id)
        made.append(section.id)
        yield tag
    finally:
        db.rollback()
        for page_id in made:
            db.query(CmsPage).filter(CmsPage.id == page_id).delete()
            db.flush()
        db.commit()
        db.close()


def _measure(browser, width: int, *, signed_in: bool, name: str, email: str = "") -> dict:
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(viewport={"width": width, "height": 900})
    try:
        if signed_in:
            login_met_sessie(page, make_session_value(email or SEEDED_ADMIN_EMAIL))
        page.goto(f"{BASE}/aanmelden" if not signed_in else f"{BASE}/")
        pagina_klaar(page)
        m = page.evaluate(MEASURE)
        print(
            f"MEASURE {name} {width}: header {m['header']['h']}, rows {m['rows']}, "
            f"logo {m['logo_img']}, account {m['account']}, scroll {m['scroll']}"
        )
        folder = os.environ.get("E2E_PRINTS")
        if folder:
            os.makedirs(folder, exist_ok=True)
            page.screenshot(path=os.path.join(folder, f"1917-{name}-{width}.png"))
        return m
    finally:
        page.close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def short(browser):
    """The seed's short menu, measured before the long one is made."""
    return {w: _measure(browser, w, signed_in=False, name="kort") for w in WIDTHS}


#: The seed's word mark, measured with master's stylesheet on 16 October 2026
#: (review of #2067): the logo stands where it stood, not only its box.
LOGO_ON_MASTER = {1200: (32, 47), 1440: (96, 47)}


def test_a_short_menu_keeps_the_header_of_before(short):
    for width, (x, y) in LOGO_ON_MASTER.items():
        assert (short[width]["logo_img"]["x"], short[width]["logo_img"]["y"]) == (x, y), width
    for width, m in short.items():
        assert m["header"]["h"] == (112 if width < 1200 else 80), (width, m["header"])
        assert m["scroll"] == width
        assert not any(_overlap(link, m["account"]) for link in m["links"]), width


def test_a_name_of_forty_characters_keeps_its_room(browser, short):
    """Review of #2067: the reserved 15rem against the widest account — a first
    name of forty characters (cut at 12rem) with its arrow, at 1 200 px, with
    the seed's short menu, which shares its row with the account. Runs before
    the long menu is made (`short` is asked first, the order of this file)."""
    email = "a" * 40 + "@example.com"  # no person: the first name is the address's first part
    m = _measure(browser, 1200, signed_in=True, name="lange-naam", email=email)
    assert m["account"]["right"] <= 1200 and m["account"]["w"] <= 240, m["account"]
    assert not [link for link in m["links"] if _overlap(link, m["account"])]
    assert m["scroll"] == 1200


@pytest.mark.parametrize("signed_in", [False, True], ids=["signed-out", "signed-in"])
@pytest.mark.parametrize("width", WIDTHS)
def test_a_long_menu_wraps_beside_the_account(browser, short, long_menu, width, signed_in):
    m = _measure(browser, width, signed_in=signed_in, name="lang-in" if signed_in else "lang")
    assert m["scroll"] == width, f"the page scrolls sideways: {m['scroll']} > {width}"
    assert m["rows"] >= 2, "fourteen pages do not fit one row"
    first_link = min(m["links"], key=lambda link: (link["y"], link["x"]))
    assert first_link["y"] >= m["logo"]["bottom"], (
        "a menu that does not fit beside the logo stands under it, on a row of its own"
    )
    if width >= 1200 and short[width]["logo_img"]:
        assert m["logo_img"]["w"] == short[width]["logo_img"]["w"], (
            "the logo gave up its width to the menu"
        )
    under = [link for link in m["links"] if _overlap(link, m["account"])]
    assert not under, f"links under the account: {under}"
    outside = [link for link in m["links"] if link["right"] > width or link["x"] < 0]
    assert not outside, f"links outside the window: {outside}"
    first_row = 64 if width < 1200 else 80
    assert m["account"]["right"] <= width and (
        m["header"]["y"] <= m["account"]["y"]
        and m["account"]["bottom"] <= m["header"]["y"] + first_row
    ), "the account stands at the top right, in the first row"


def test_a_section_on_a_wrapped_row_opens_inside_the_window(browser, long_menu):
    """Review of #2067: the section of #2024 stands on the last row of a wrapped
    menu; its pages open under it, inside the window and over no account."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL))
        page.goto(f"{BASE}/")
        pagina_klaar(page)
        section = page.locator(
            f"#site-nav-breed [data-menu-section]:has(a[href$='/sectie-{long_menu}'])"
        )
        arrow = section.locator("[data-menu-section-button]")
        first_row = page.locator("#site-nav-breed > a").first.bounding_box()["y"]
        assert arrow.bounding_box()["y"] > first_row, "the section stands on a later row"
        arrow.click()
        pages = section.locator("[data-menu-section-pages]")
        pages.wait_for(state="visible")
        box = pages.bounding_box()
        account = page.locator("[data-site-account]").bounding_box()
        print(
            f"MEASURE wrapped section: list x {box['x']:.0f}..{box['x'] + box['width']:.0f} y {box['y']:.0f}"
        )
        assert box["x"] >= 0 and box["x"] + box["width"] <= 1440
        assert box["y"] >= arrow.bounding_box()["y"] + arrow.bounding_box()["height"]
        assert not (
            box["x"] < account["x"] + account["width"]
            and account["x"] < box["x"] + box["width"]
            and box["y"] < account["y"] + account["height"]
            and account["y"] < box["y"] + box["height"]
        )
        assert pages.evaluate(
            "el => document.elementFromPoint(el.getBoundingClientRect().x + 20, el.getBoundingClientRect().y + 20)?.closest('[data-menu-section-pages]') === el"
        ), "the list is painted, not clipped under the content"
    finally:
        page.close()

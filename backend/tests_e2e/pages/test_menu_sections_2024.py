"""E2E: a section in the site's menu (CR-17 phase 6, AC12; #2024).

Koen, 16 October 2026, "1a, 2a, 3a": from 768 px the section's name opens its
page and the arrow beside it opens its pages — by click, by tap, by keyboard;
on a phone the drawer shows them always, indented under the section; the way
back from a page under a section names it.

Walked at 1 100 px and at 1 440 px (the header on one row, the section last in
the menu, where a drop-down is nearest the window's edge) and at 390 px.
`MEASURE` lines print what was measured; set `E2E_PRINTS` to a folder to keep a
print of each (outside the repository).

Broken on purpose (16 October 2026): `@click="sub = !sub"` taken off the arrow →
the drop-down never opens and the wide walk is red; `site-drawer-sub` taken out
of the stylesheet → the drawer's indent is 0 and the phone walk is red; `or pad
in within` taken out of `navlink` → the section is not current on its page.
After the review of #2057: `place()` not called → the list pushed to the edge
leaves the window (B2); the `@focusout` taken out → Tab past the last page
leaves it open (B3).
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def setup():
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.cms.api import publish, update_page
    from app.domains.cms.service import create_page
    from app.schemas.cms import CmsPageCreate, CmsPageUpdate

    tag = secrets.token_hex(3)
    db = SessionLocal()
    made = {}
    try:
        # Last in the menu: the drop-down stands nearest the window's right edge.
        for key, title, order in (
            ("section", "Over ons", 9_000),
            ("bestuur", "Het bestuur van de vereniging", 1),
            ("werking", "Werking", 2),
        ):
            page = create_page(
                db, CmsPageCreate(title=title, slug=f"{key}-{tag}", sort_order=order)
            )
            publish(db, page.id)
            made[key] = page.id
        for key in ("bestuur", "werking"):
            update_page(db, made[key], CmsPageUpdate(parent_id=made["section"]))
        update_page(db, made["bestuur"], CmsPageUpdate(menu_label="Bestuur"))
        yield {"tag": tag, **made}
    finally:
        # The walk leaves no section behind: a second run on the same database
        # would otherwise show two "Over ons" in every later print.
        from app.domains.cms.api import CmsPage

        db.rollback()
        for key in ("bestuur", "werking", "section"):
            if key in made:
                db.query(CmsPage).filter(CmsPage.id == made[key]).delete()
                db.flush()
        db.commit()
        db.close()


def _print(page, name: str) -> None:
    folder = os.environ.get("E2E_PRINTS")
    if folder:
        os.makedirs(folder, exist_ok=True)
        page.screenshot(path=os.path.join(folder, f"2024-{name}.png"))


@pytest.mark.parametrize("width", [1100, 1300, 1440])
def test_the_arrow_opens_the_sections_pages(setup, width):
    tag = setup["tag"]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 900})
        try:
            page.goto(f"{BASE}/werking-{tag}")
            pagina_klaar(page)
            back = page.locator("main a", has_text="‹ Over ons").first
            assert back.is_visible(), "the way back names the section"
            assert back.get_attribute("href").endswith(f"/section-{tag}")

            section = page.locator(f"#site-nav-breed a[href$='/section-{tag}']")
            arrow = page.locator(
                f"#site-nav-breed [aria-controls='menu-sectie-{setup['section']}']"
            )
            pages = page.locator(f"#menu-sectie-{setup['section']}")
            assert section.is_visible() and arrow.is_visible()
            assert section.get_attribute("aria-current") == "page", (
                "on a page under the section, the section is where the visitor is"
            )
            assert not pages.is_visible(), "closed until asked"

            arrow.click()
            pages.wait_for(state="visible")
            assert arrow.get_attribute("aria-expanded") == "true"
            box = pages.bounding_box()
            head = page.locator("header.site-header").bounding_box()
            link_box = arrow.bounding_box()
            print(
                f"MEASURE {width}: drop-down x {box['x']:.0f}..{box['x'] + box['width']:.0f} "
                f"y {box['y']:.0f}, arrow bottom {link_box['y'] + link_box['height']:.0f}, "
                f"header bottom {head['y'] + head['height']:.0f}"
            )
            assert box["x"] >= 0 and box["x"] + box["width"] <= width, "inside the window"
            assert box["y"] >= link_box["y"] + link_box["height"], "under the arrow"
            names = pages.locator("a").all_inner_texts()
            assert names == ["Bestuur", "Werking"], names
            _print(page, f"open-{width}")

            page.keyboard.press("Escape")
            pages.wait_for(state="hidden")
            assert page.evaluate("document.activeElement.getAttribute('aria-controls')") == (
                f"menu-sectie-{setup['section']}"
            ), "Escape gives the focus back to the arrow"

            # Review B3 of #2057: Tab past the last page closes the list.
            page.keyboard.press("Enter")
            pages.wait_for(state="visible")
            for _ in names:
                page.keyboard.press("Tab")
            page.keyboard.press("Tab")
            pages.wait_for(state="hidden")

            # Review B2: pushed to the window's right edge, the list opens to
            # the left — the open list measured, not a width written twice.
            pages.locator("xpath=..").evaluate(
                "(el) => { el.style.marginLeft = (window.innerWidth - el.getBoundingClientRect().right - 40) + 'px' }"
            )
            arrow.click()
            pages.wait_for(state="visible")
            page.wait_for_function(
                "(el) => el.getBoundingClientRect().right <= window.innerWidth",
                arg=pages.element_handle(),
            )
            edge = pages.bounding_box()
            print(
                f"MEASURE {width} at the edge: drop-down x {edge['x']:.0f}..{edge['x'] + edge['width']:.0f}"
            )
            assert edge["x"] >= 0 and edge["x"] + edge["width"] <= width, "inside the window"
            pages.locator("a", has_text="Bestuur").click()
            page.wait_for_url(f"**/bestuur-{tag}")
            pagina_klaar(page)
            assert page.locator("h1").inner_text() == "Het bestuur van de vereniging"
        finally:
            browser.close()


def test_the_drawer_shows_the_sections_pages_indented(setup):
    tag = setup["tag"]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            page.goto(f"{BASE}/werking-{tag}")
            pagina_klaar(page)
            page.locator("[data-menu-button]").click()
            drawer = page.locator("#site-nav-mobiel")
            drawer.wait_for(state="visible")
            section = drawer.locator(f"a[href$='/section-{tag}']")
            sub = drawer.locator(f"a[href$='/bestuur-{tag}']")
            current = drawer.locator(f"a[href$='/werking-{tag}']")
            section.scroll_into_view_if_needed()
            assert section.is_visible() and sub.is_visible() and current.is_visible()

            indent = page.evaluate(
                """([a, b]) => {
                    const text = (el) => { const r = document.createRange();
                        r.selectNodeContents(el); return r.getBoundingClientRect().x; };
                    return text(b) - text(a);
                }""",
                [section.element_handle(), sub.element_handle()],
            )
            order = drawer.locator("a").evaluate_all("els => els.map(e => e.getAttribute('href'))")
            at = next(i for i, h in enumerate(order) if h.endswith(f"/section-{tag}"))
            print(
                f"MEASURE 390: indent {indent:.0f} px; rows after the section {order[at + 1 : at + 3]}"
            )
            assert indent >= 20, "indented under the section"
            assert [h.rsplit("/", 1)[1] for h in order[at + 1 : at + 3]] == [
                f"bestuur-{tag}",
                f"werking-{tag}",
            ]
            assert current.get_attribute("aria-current") == "page"
            for el in (section, sub):
                assert el.bounding_box()["height"] >= 44, "a touch target"
            _print(page, "drawer-390")
        finally:
            browser.close()

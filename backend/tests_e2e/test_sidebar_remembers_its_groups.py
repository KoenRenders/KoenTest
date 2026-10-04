"""E2E: the admin sidebar remembers its groups and shows the active item (#1526).

Every click loads a page, and the sidebar used to start from scratch: the groups
the user had folded came back open, and the sidebar scrolled to the top, so an
active item lower in the list was out of view.

- a folded group stays folded on the next page, boosted click or reload; the
  group of the active item is open whatever was stored;
- in a sidebar too short for its items, the item just clicked is inside the
  sidebar's visible box after the load (its rect against the box's);
- with storage blocked, the sidebar renders with every group open and a click on
  a heading throws nothing.

Red against master `f0323657` for the first two: the folded group came back
open, and the clicked item stood below the box.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

_OPEN = """name => {
  const d = [...document.querySelectorAll('#admin-nav-zijbalk details')]
    .find(g => g.querySelector('summary').textContent.trim() === name);
  return d ? d.open : null;
}"""

_IN_BOX = """href => {
  const nav = document.querySelector('#admin-nav-zijbalk');
  const a = nav.querySelector(`a[href="${href}"]`);
  const r = a.getBoundingClientRect(), b = nav.getBoundingClientRect();
  return {item: [Math.round(r.top), Math.round(r.bottom)], box: [Math.round(b.top), Math.round(b.bottom)],
          scrolled: nav.scrollTop, current: a.getAttribute('aria-current'), page: scrollY};
}"""

_NO_STORAGE = """
for (const m of ['getItem', 'setItem', 'removeItem']) {
  Storage.prototype[m] = function () { throw new DOMException('blocked', 'SecurityError'); };
}
"""


@pytest.fixture(scope="module")
def browser_and_session():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _page(browser_and_session, height: int = 900, init: str | None = None):
    b, session = browser_and_session
    page = b.new_page(base_url=BASE, viewport={"width": 1920, "height": height})
    if init:
        page.add_init_script(init)
    login_met_sessie(page, session)
    page.goto("/admin/betalingen")
    pagina_klaar(page)
    return page


def _heading(page, name: str):
    return page.locator("#admin-nav-zijbalk summary").filter(has_text=name)


def _go(page, href: str) -> None:
    page.locator(f'#admin-nav-zijbalk a[href="{href}"]').click()
    page.wait_for_url(f"**{href}")
    pagina_klaar(page)


def test_a_folded_group_stays_folded_and_the_active_group_is_open(browser_and_session):
    page = _page(browser_and_session)
    _heading(page, "Communicatie").click()
    _heading(page, "Inhoud").click()
    assert page.evaluate(_OPEN, "Communicatie") is False
    assert page.evaluate(_OPEN, "Inhoud") is False

    # Inhoud's item is hidden while folded; open it in code, which is not stored.
    page.evaluate(
        "() => [...document.querySelectorAll('#admin-nav-zijbalk details')].forEach(d => d.open = true)"
    )
    _go(page, "/admin/paginas")
    seen = {g: page.evaluate(_OPEN, g) for g in ("Communicatie", "Inhoud", "Werking")}
    print("MEASURE boosted", seen)
    assert seen == {"Communicatie": False, "Inhoud": True, "Werking": True}, (
        "Communicatie stays folded; Inhoud holds the active item, so it is open"
    )

    page.reload()
    pagina_klaar(page)
    seen = {g: page.evaluate(_OPEN, g) for g in ("Communicatie", "Inhoud", "Werking")}
    print("MEASURE reload", seen)
    assert seen == {"Communicatie": False, "Inhoud": True, "Werking": True}
    page.close()


def test_the_clicked_item_is_in_the_sidebar_box_after_the_load(browser_and_session):
    page = _page(browser_and_session, height=420)
    before = page.evaluate(_IN_BOX, "/admin/info")
    assert before["item"][0] >= before["box"][1], f"the item starts below the box: {before}"

    _go(page, "/admin/info")
    after = page.evaluate(_IN_BOX, "/admin/info")
    print("MEASURE", before, after)
    assert after["current"] == "page"
    assert after["box"][0] <= after["item"][0] and after["item"][1] <= after["box"][1], after
    assert after["page"] == 0, "the page itself does not scroll"
    page.close()


def test_with_storage_blocked_the_sidebar_renders_its_defaults(browser_and_session):
    page = _page(browser_and_session, init=_NO_STORAGE)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    groups = page.evaluate(
        "() => [...document.querySelectorAll('#admin-nav-zijbalk details')].map(d => d.open)"
    )
    assert len(groups) >= 5 and all(groups), groups
    _heading(page, "Communicatie").click()
    assert page.evaluate(_OPEN, "Communicatie") is False, "folding still works, unremembered"
    _go(page, "/admin/paginas")
    assert page.evaluate(_OPEN, "Communicatie") is True, "nothing was stored"
    assert errors == []
    page.close()

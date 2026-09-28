"""Every filter bar shrinks without overlap and keeps its desktop shape (#1202).

`ui.filter_bar` put its controls on one line and trusted that they fit. Three
symptoms of that came up on one day:

1. **Growing** — the kind filter on Media could not take a fourth kind (#1194,
   solved there: the chips became a select list).
2. **Shrinking** — at 390 px the search field of `/admin/betalingen` slid 29 px
   under the *AI · Betalingen* button next to the form. The form carried
   `min-w-0`, so it was squeezed to 199 px while the field inside it kept its
   224 px minimum.
3. **Hidden margin** — `space-y-3` put a 12 px margin on the first visible row
   whenever hidden inputs came before it (the sort fields of the e-mail log and
   the member changes). On those screens it collapsed into the page header's
   larger margin, so nobody saw it — but it was there, and on the activity's
   payments tab it once put the button 14 px out of line (#1197).

The repair: the form keeps its own content as its minimum and the row next to
it may wrap, so the button takes its own line when the two do not fit; and the
bar spaces its children with `gap`, which ignores a child that generates no box.

The screens are **every** filter bar that a seeded backend can open, not only
the ones where a symptom was reported. Measured on 27 September 2026 before and
after the change: at 1440 px every bar had exactly the same geometry; at 390 px
the payments screen and the activity's payments tab were the only overlaps.

Broken on purpose to check that these tests can go red (27 September 2026):
- `min-w-0` put back on the payments form and `flex-wrap` taken off its row →
  4 failed: the overlap test and the own-line test, each on `/admin/betalingen`
  and on the activity tab.
- `flex-wrap` kept but `min-w-0` put back → the same 4 failed. The wrap alone
  does nothing while the form may shrink to zero: both halves are needed.
- `space-y-3` put back in `filter_bar` → 3 failed on the margin test: the
  e-mail log and the member changes (the hidden sort fields), and the
  workbench, whose second visible row gets its 12 px from `gap` now.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, pagina_klaar  # noqa: E402

#: Every screen with a `ui.filter_bar` that the e2e seed can open. `TAB` is the
#: payments tab of the first activity in the list.
TAB = "activiteit-tab"
SCREENS = [
    "/admin/tenants",
    "/admin/e-maillog",
    "/admin/vergaderingen",
    "/admin/organisaties",
    "/admin/paginas",
    "/admin/ledenwijzigingen",
    "/admin/betalingen",
    TAB,
    "/admin/formulieren",
    "/admin/werkbank",
    "/admin/rapporten",
    "/admin/ontwerpen",
    "/admin/nieuwsbrieven/abonnees",
    "/admin/media?kind=activity_photo",
    "/admin/gebruikers",
    "/admin/leden",
    "/admin/nieuwsbrieven",
    "/admin/activiteiten",
    "/admin/design-system",
]

_MEASURE = """() => {
  const f = document.querySelector('form[hx-headers*="X-Raak-Filter"]');
  if (!f) return null;
  const box = e => { const b = e.getBoundingClientRect();
                     return {l: b.left, t: b.top, r: b.right, b: b.bottom, w: b.width}; };
  const shown = e => { const b = e.getBoundingClientRect(); return b.width > 0 && b.height > 0; };
  const label = e => e.getAttribute('name') || e.tagName.toLowerCase();
  const controls = [...f.querySelectorAll('input,select,textarea,a,button')].filter(shown)
    .map(e => ({name: label(e), ...box(e)}));
  // Only a flex row puts something NEXT to the form; in any other parent the
  // siblings are the page header and the list, above and below it.
  const ps = getComputedStyle(f.parentElement);
  const inRow = ps.display.includes('flex') && ps.flexDirection.startsWith('row');
  const neighbours = [...f.parentElement.children].filter(x => inRow && x !== f && shown(x))
    .map(x => ({name: (x.textContent || '').trim().split('\\n')[0], ...box(x)}));
  const rows = [...f.children].filter(shown)
    .map(x => parseFloat(getComputedStyle(x).marginTop));
  const search = f.querySelector('input[type=search]');
  return {form: box(f), controls, neighbours, inRow, rowMargins: rows,
          search: search ? box(search).w : null};
}"""


@pytest.fixture(scope="module")
def browser_page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        login_als_admin(page, email, make_session_value(email))
        yield page
        browser.close()


def _measure(page, screen: str, width: int) -> dict:
    page.set_viewport_size({"width": width, "height": 900})
    if screen == TAB:
        page.goto("/admin/activiteiten")
        path = page.evaluate(
            r"""Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.getAttribute('href'))
                    .find(h => /^\/admin\/activiteiten\/\d+$/.test(h)) || null"""
        )
        assert path, "no activity in the list to open the payments tab of"
        page.goto(f"{path}/betalingen")
    else:
        page.goto(screen)
    pagina_klaar(page)
    m = page.evaluate(_MEASURE)
    assert m is not None, f"no filter bar on {screen}"
    assert m["controls"], f"the filter bar on {screen} shows no control — measuring nothing"
    return m


def _overlap(a: dict, b: dict) -> bool:
    return a["l"] < b["r"] and b["l"] < a["r"] and a["t"] < b["b"] and b["t"] < a["b"]


@pytest.mark.parametrize("screen", SCREENS)
def test_nothing_overlaps_on_a_phone(browser_page, screen):
    """Symptom 2: at 390 px no control overlaps what stands next to the form,
    and none sticks out of its own form."""
    m = _measure(browser_page, screen, 390)
    clash = [
        (c["name"], n["name"]) for c in m["controls"] for n in m["neighbours"] if _overlap(c, n)
    ]
    assert not clash, f"{screen}: control under a neighbour of the form: {clash}"
    outside = [
        c["name"]
        for c in m["controls"]
        if c["r"] > m["form"]["r"] + 1 or c["l"] < m["form"]["l"] - 1
    ]
    assert not outside, f"{screen}: sticks out of the filter form: {outside}"


@pytest.mark.parametrize("screen", ["/admin/betalingen", TAB])
def test_on_a_desktop_the_button_stays_beside_the_form(browser_page, screen):
    """Wrapping is for a phone. At 1440 px the *AI · Betalingen* button still
    stands to the right of the form, on its line — the only thing this change
    could move on a desktop. The other bars have nothing next to their form;
    their 1440 px geometry was compared before and after, and was identical."""
    m = _measure(browser_page, screen, 1440)
    assert m["inRow"] and m["neighbours"], (
        f"{screen}: nothing next to the filter form — is the Raakje button on?"
    )
    for n in m["neighbours"]:
        assert n["l"] >= m["form"]["r"], (
            f"{screen}: {n['name']!r} wrapped under the form at 1440 px"
        )
        assert n["t"] < m["form"]["b"], f"{screen}: {n['name']!r} stands below the form at 1440 px"


@pytest.mark.parametrize("screen", ["/admin/betalingen", TAB])
def test_on_a_phone_the_button_takes_its_own_line(browser_page, screen):
    """The other half: at 390 px the button goes UNDER the form instead of
    squeezing it. Without this, the overlap test would also pass if the button
    simply disappeared."""
    m = _measure(browser_page, screen, 390)
    assert m["inRow"] and m["neighbours"], (
        f"{screen}: nothing next to the filter form — is the Raakje button on?"
    )
    for n in m["neighbours"]:
        assert n["t"] >= m["form"]["b"], f"{screen}: {n['name']!r} is not below the form at 390 px"
        assert n["r"] <= 390, f"{screen}: {n['name']!r} sticks out of the screen"


@pytest.mark.parametrize("screen", SCREENS)
def test_no_row_of_a_filter_bar_carries_a_margin(browser_page, screen):
    """Symptom 3: the rows of a bar are spaced by `gap`, so none carries a
    margin — also not the first visible one after hidden inputs."""
    m = _measure(browser_page, screen, 1440)
    assert m["rowMargins"], f"{screen}: no visible row in the filter bar"
    assert all(x == 0 for x in m["rowMargins"]), (
        f"{screen}: a row of the filter bar carries a top margin: {m['rowMargins']}"
    )


@pytest.mark.parametrize("screen", SCREENS)
def test_the_search_field_keeps_its_minimum(browser_page, screen):
    """The shared 14rem floor stays (#1079/#996): the repair made the form
    respect it, it did not lower it."""
    m = _measure(browser_page, screen, 390)
    if m["search"] is None:
        pytest.skip(f"{screen} has no search field")
    assert m["search"] >= 224, f"{screen}: search field {m['search']} px wide"

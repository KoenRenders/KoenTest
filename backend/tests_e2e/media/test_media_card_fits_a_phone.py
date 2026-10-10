"""#1265 — a media card fits a 390 px phone and the page does not scroll sideways.

Measured on 27 September 2026 while building #1194: on `/admin/media` with the
page images, the document was 403 px wide at 390 px. The overflow was the card's
edit side — the action bar, the title field and the row Volgorde / Actief /
dimensions. The row had no `flex-wrap`, so its narrowest width was the whole row
on one line, and the `flex-1` column beside the thumbnail could not shrink below
it. #1236 needed `min-w-0` as well; here it did not (measured below).

Why an e2e test and not a render test: the markup was valid. Only a browser
knows how wide that row is and whether it fits.

The test first counts what it measures — a card, its Opslaan button, the two
reorder arrows and the Actief box — so an empty screen cannot pass as "fits".

Broken on purpose (28 September 2026):
- `flex-wrap` taken off the row → the phone test failed: the page 403 px wide,
  "240×150" sticking out. The desktop test stayed green.
- `min-w-0` added on the column and then taken off again → no difference: the
  wrap alone is the repair, so `min-w-0` is not in it.

Desktop geometry, measured before and after on every media kind at 1440 and
1280 px: identical, element for element (27 boxes on the page-image cards; the
seed has no sponsor or logo cards).
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, pagina_klaar  # noqa: E402

PHONE = 390
SCREEN = "/admin/media?kind=page_image"

_MEASURE = """(limit) => {
  const list = document.querySelector('#me-lijst');
  if (!list) return null;
  const card = list.querySelector('form');
  const box = e => { const r = e.getBoundingClientRect();
                     return {l: Math.round(r.left), t: Math.round(r.top),
                             r: Math.round(r.right), b: Math.round(r.bottom)}; };
  const shown = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const offenders = [...list.querySelectorAll('*')].filter(shown)
    .filter(e => Math.round(e.getBoundingClientRect().right) > limit)
    .map(e => `${e.tagName.toLowerCase()} "${(e.innerText || e.value || '').trim().slice(0, 30)}" right=${box(e).r}`);
  const row = card ? card.querySelector('input[name="is_active"]').closest('div') : null;
  return {
    doc: document.documentElement.scrollWidth,
    cards: list.querySelectorAll('form').length,
    save: card ? [...card.querySelectorAll('button')].filter(b => /Opslaan/.test(b.innerText) && shown(b)).length : 0,
    arrows: card ? card.querySelectorAll('[hx-post$="/verplaats"]').length : 0,
    active: card ? card.querySelectorAll('input[name="is_active"]').length : 0,
    offenders,
    rowChildren: row ? [...row.children].filter(shown).map(box) : [],
  };
}"""


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        login_als_admin(p, email, make_session_value(email))
        yield p
        browser.close()


def _measure(page, width: int) -> dict:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(SCREEN)
    pagina_klaar(page)
    m = page.evaluate(_MEASURE, width)
    assert m is not None, "no media list on the screen"
    assert m["cards"] >= 1, "no media card on the screen — is the e2e seed loaded?"
    assert m["save"] == 1 and m["arrows"] == 2 and m["active"] == 1, (
        f"the card's controls are not all there: {m}"
    )
    return m


def test_the_media_card_fits_a_phone(page):
    m = _measure(page, PHONE)
    assert m["doc"] <= PHONE, (
        f"the page is {m['doc']} px wide at {PHONE} px; sticking out: {m['offenders']}"
    )
    assert not m["offenders"], f"sticking out of the screen: {m['offenders']}"


def test_on_a_desktop_the_row_stays_on_one_line(page):
    """The other half: at 1440 px Volgorde, Actief and the dimensions stay on
    one line, as they did before the fix."""
    m = _measure(page, 1440)
    tops = {c["t"] for c in m["rowChildren"]}
    assert len(m["rowChildren"]) >= 3, m["rowChildren"]
    assert max(tops) - min(tops) <= 6, f"the row wrapped at 1440 px: {m['rowChildren']}"

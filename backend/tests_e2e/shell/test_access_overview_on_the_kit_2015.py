"""E2E: the overview of every workspace on the kit's list table (#2015).

*Toegang over alle werkruimtes* (from Gebruikers, platform administration) was a
hand-written table without a scroll wrapper. Measured on 15 October 2026 by the
builder of #1873 at 390 px: 515 px wide, the page 166 px sideways, Rol and Status
outside the card. On the kit's table it is the stacked list on a phone that
every other list is.

At 390 and 1280 px, read from the rendered page: the page does not scroll
sideways, and in every row the account, the workspace, the role and the status
are visible and stand inside the table's frame.

Set `E2E_PRINTS` to a folder to keep a print at each width (outside the
repository). Nothing here changes data but the operator it signs in with.

Red on master `ce218671` (15 October 2026): at 390 px the page is wider than the
window, and the table has no kit frame to measure.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import PLATFORM, login_met_sessie, pagina_klaar  # noqa: E402

PAGE = "/admin/gebruikers/alle-werkruimtes"

_MEASURE = """() => {
  const frame = document.querySelector('[data-table-frame]');
  if (!frame) return {frame: null, scroll: document.documentElement.scrollWidth, width: innerWidth};
  const right = Math.round(frame.getBoundingClientRect().right);
  const rows = [...frame.querySelectorAll('tbody tr[data-access-row]')].map(tr =>
    ['name', 'context', 'more', 'status'].map(part => {
      const cell = tr.querySelector(`[data-cell="${part}"]`);
      const box = cell.getBoundingClientRect();
      return {part, shown: cell.checkVisibility() && box.width > 0, inside: Math.round(box.right) <= right + 1};
    }));
  return {frame: right, rows, scroll: document.documentElement.scrollWidth, width: innerWidth};
}"""


@pytest.fixture(scope="module")
def operator():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole

    email = f"e2e-2015-{secrets.token_hex(3)}@example.org"
    db = SessionLocal()
    try:
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db.commit()
        user_id = user.id
    finally:
        db.close()
    yield make_session_value(email)
    db = SessionLocal()
    try:
        db.query(UserRole).filter(UserRole.user_id == user_id).delete(synchronize_session=False)
        db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_the_overview_fits_and_every_column_is_reachable(browser, operator, width):
    page = browser.new_page(
        base_url=PLATFORM, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    try:
        login_met_sessie(page, operator, PLATFORM)
        page.goto(PAGE)
        pagina_klaar(page)
        m = page.evaluate(_MEASURE)
        print(f"MEASURE access overview {width}", m)
        folder = os.environ.get("E2E_PRINTS")
        if folder:
            os.makedirs(folder, exist_ok=True)
            page.screenshot(path=os.path.join(folder, f"2015-overzicht-{width}.png"))
    finally:
        page.close()

    assert m["scroll"] <= m["width"], f"the page is {m['scroll']} px wide at {width}"
    assert m["frame"] is not None, "the overview is not on the kit's table"
    assert m["rows"], "no row to measure: the seed has roles, so the page is broken"
    hidden = [cells for cells in m["rows"] if not all(c["shown"] and c["inside"] for c in cells)]
    assert not hidden, f"a column is hidden or outside the frame: {hidden[:2]}"

"""E2E: the page editor's toolbars stay in view while a long page scrolls (#1391 W3).

CR-11 W3: the page's own button row and Trix's toolbar stick under the sticky
header (title + Opslaan). Measured as the issue asks, at 390 and 1280 px: after
scrolling 2 000 px in a long page, the button "Afbeelding" and Trix's toolbar
are inside the viewport, and neither overlaps the header.

Proven red against master `112ed593` (served from an export of it): after the
scroll the button row had gone off the top of the screen.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1391"

_MEASURE = """() => {
  const r = e => { const b = e.getBoundingClientRect(); return {top: Math.round(b.top), bottom: Math.round(b.bottom)}; };
  const kop = document.querySelector('#cp-detail .sticky');
  const knop = [...document.querySelectorAll('#cp-detail button')].find(b => b.textContent.trim() === 'Afbeelding');
  const trix = document.querySelector('#cp-detail trix-toolbar');
  return {scroll: Math.round(scrollY), vh: innerHeight, kop: r(kop), knop: r(knop), trix: r(trix),
          doc: document.documentElement.scrollWidth, vw: innerWidth};
}"""


def _long_page() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.cms.models import CmsPage

    tag = secrets.token_hex(3)
    body = "".join(
        f"<div>Alinea {n}: een regel tekst om de pagina lang te maken.</div>" for n in range(250)
    )
    db = SessionLocal()
    try:
        page = CmsPage(title=f"Lange pagina {tag}", slug=f"lang-{tag}", content=body)
        db.add(page)
        db.commit()
        return page.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page_id = _long_page()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, page_id, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_the_toolbars_stay_in_view_under_the_header(browser, width):
    b, page_id, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        login_met_sessie(page, session_value)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector("#cp-detail trix-toolbar")
        page.evaluate("() => window.scrollTo(0, 2000)")
        page.wait_for_function("() => Math.round(scrollY) === 2000")
        page.evaluate(
            "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
        )
        m = page.evaluate(_MEASURE)
        print(f"MEASURE @{width}", m)
        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.screenshot(path=f"{SHOTS}/{width}-w3-pagina.png")

        assert m["scroll"] == 2000, "the page is long enough to scroll 2 000 px"
        assert 0 <= m["knop"]["top"] and m["knop"]["bottom"] <= m["vh"], f"'Afbeelding' left: {m}"
        assert 0 <= m["trix"]["top"] and m["trix"]["bottom"] <= m["vh"], f"Trix's toolbar left: {m}"
        assert m["knop"]["top"] >= m["kop"]["bottom"] - 1, (
            f"the button row overlaps the header: {m}"
        )
        assert m["trix"]["top"] >= m["knop"]["bottom"] - 1, f"Trix's toolbar overlaps the row: {m}"
        assert m["doc"] <= m["vw"], m
    finally:
        page.close()

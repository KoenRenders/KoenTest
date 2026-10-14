"""E2E: the page editor's toolbar stays in view while a long page scrolls (#1391 W3).

CR-11 W3: the tools stick under the sticky header. Snede 3 (#1671) carried the
behaviour to the document editor's toolbar: sticky under the shell's header,
whose height the shell names in --shell-kop. Measured as the issue asks, at
390 and 1280 px: after scrolling 2 000 px in a long page, the toolbar and her
"Blok invoegen" are inside the viewport, and neither overlaps the header.

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
  const kop = document.querySelector('header.sticky');
  const bar = document.querySelector('#cp-document .de-bar');
  const knop = [...bar.querySelectorAll('.de-btn')].find(b => b.textContent.trim() === 'Blok invoegen ▾');
  return {scroll: Math.round(scrollY), vh: innerHeight, kop: r(kop), bar: r(bar), knop: knop ? r(knop) : null,
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
        page.wait_for_selector("#cp-document .tiptap")
        # Scroll PAST the toolbar — 400 px beyond her own place in the
        # document, so she must stick to stay in reach. A fixed 2 000 px
        # does not reach the editor on a phone, where the page stacks
        # three times as tall.
        page.evaluate(
            "() => { const bar = document.querySelector('#cp-document .de-bar');"
            " window.scrollTo(0, Math.round(bar.getBoundingClientRect().top + scrollY) + 400); }"
        )
        page.wait_for_function("() => scrollY > 100")
        page.evaluate(
            "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
        )
        m = page.evaluate(_MEASURE)
        print(f"MEASURE @{width}", m)
        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.screenshot(path=f"{SHOTS}/{width}-w3-pagina.png")

        assert m["scroll"] > 100, "the page scrolled"
        # The editor's toolbar stays in reach — the tools of a long page
        # (snede 3: the document editor kept #1391 W3's behaviour, sticky
        # under the shell's header, whose height the shell names).
        assert m["bar"] is not None and 0 <= m["bar"]["top"] and m["bar"]["bottom"] <= m["vh"], (
            f"the toolbar left the viewport: {m}"
        )
        assert m["knop"] is not None and m["knop"]["bottom"] <= m["vh"], (
            f"'Blok invoegen' left: {m}"
        )
        assert m["bar"]["top"] >= m["kop"]["bottom"] - 1, f"the toolbar overlaps the header: {m}"
        assert m["doc"] <= m["vw"], m
    finally:
        page.close()

"""E2E: the media library's tree at 1 440 and 390 px (CR-15 phase 1, #1470).

Back office is desktop-first (CR-15 R8): judged at 1 440 px, and at 390 px only
"nothing breaks".

Measured:
- at 1 440 px the tree and the cards stand side by side: the tree column's
  width, the card column's width, no overlap;
- at 390 px the document's scroll width equals the viewport's, the tree stands
  above the cards;
- a tag chosen in the tree lists its pictures, and the card's tag choice opens.

Screenshots go outside the repo.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1470"

_LAYOUT = """() => {
  const r = e => { const b = e.getBoundingClientRect(); return {x: Math.round(b.x), right: Math.round(b.right), y: Math.round(b.y), w: Math.round(b.width)}; };
  const boom = document.querySelector('#me-boom');
  const lijst = document.querySelector('#me-lijst');
  // The widest right edge of anything in the list: a card can clip what
  // overflows it, so the page width alone does not show a button pushed off.
  const verst = Math.max(...[...lijst.querySelectorAll('*')].map(e => Math.round(e.getBoundingClientRect().right)));
  return {page: [document.documentElement.scrollWidth, innerWidth], boom: r(boom), lijst: r(lijst), verst};
}"""


def _situation() -> tuple[int, str]:
    """A tag with a child tag and a picture with two tags — a long tag line."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.media.api import create_tag, tag_asset
    from app.domains.media.models import MediaAsset

    db = SessionLocal()
    try:
        mark = secrets.token_hex(2)
        parent = create_tag(db, f"Jeugd {mark}")
        child = create_tag(db, f"Kamp {mark}", parent_id=parent.id)
        asset = MediaAsset(
            # Not `page_image`: the CMS insert e2e takes the library's FIRST page
            # picture, and this fake one (no real bytes) broke it. A tag works on
            # any kind; a design image of no activity is offered nowhere.
            kind="design_image",
            title=f"tenten {mark}",
            sort_order=0,
            is_active=True,
            content_type="image/jpeg",
            byte_size=10,
            width=10,
            height=10,
            data=b"x",
            thumbnail=b"y",
        )
        db.add(asset)
        db.commit()
        tag_asset(db, asset.id, child.id)
        tag_asset(db, asset.id, create_tag(db, f"Sint en Piet {mark}").id)
        return parent.id, mark
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser_and_tag():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag_id, mark = _situation()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), tag_id, mark
        b.close()


def _page(browser_and_tag, width: int, path: str):
    b, session, _tag, _mark = browser_and_tag
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    page.goto(path)
    pagina_klaar(page)
    return page


def _shot(page, name: str) -> None:
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/{name}.png")


def test_at_1440_the_tree_and_the_cards_stand_side_by_side(browser_and_tag):
    _b, _s, tag_id, mark = browser_and_tag
    page = _page(browser_and_tag, 1440, f"/admin/media?tag={tag_id}")
    m = page.evaluate(_LAYOUT)
    titles = page.evaluate("() => [...document.querySelectorAll('#me-lijst img')].map(i => i.alt)")
    print("MEASURE 1440", m, titles)
    _shot(page, "1440-boom-en-kaarten")
    page.close()

    assert m["page"][0] <= m["page"][1], m
    assert m["boom"]["right"] <= m["lijst"]["x"], f"side by side, no overlap: {m}"
    assert abs(m["boom"]["y"] - m["lijst"]["y"]) < 120, f"the same row: {m}"
    assert f"tenten {mark}" in titles, "the parent tag lists the picture of its child tag"


def test_at_390_nothing_breaks(browser_and_tag):
    _b, _s, tag_id, _mark = browser_and_tag
    page = _page(browser_and_tag, 390, f"/admin/media?tag={tag_id}")
    m = page.evaluate(_LAYOUT)
    page.locator("#me-lijst details summary").first.click()
    open_ok = page.evaluate("() => document.querySelector('#me-lijst details').open")
    print("MEASURE 390", m, "tag choice opens:", open_ok)
    _shot(page, "390-boom-boven-kaarten")
    page.close()

    assert m["page"][0] == m["page"][1], f"no horizontal scroll: {m}"
    assert m["verst"] <= m["page"][1], f"something in the list sticks out: {m}"
    assert m["boom"]["y"] < m["lijst"]["y"], "the tree stands above the cards"
    assert open_ok, "the card's tag choice opens"

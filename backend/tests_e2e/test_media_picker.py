"""E2E: the media picker, live on the design-system page (CR-15 phase 2, #1472).

Back office is desktop-first (CR-15 R8): judged at 1 440 px, and at 390 px only
"nothing breaks".

Measured:
- at 1 440 px the modal holds the tree and the grid side by side: no overlap,
  the same row, five thumbnails to a row;
- at 390 px the modal's panel fits the viewport, nothing in it sticks out, the
  tree is folded and the grid starts on the first screen. The page's own scroll
  width is not the measure here: the design-system page is 392 px wide at 390
  without the picker (its "Naar de formulierbouwer" demo link), on master too;
- choosing a thumbnail sets the hidden field to the picture's id, shows its
  thumbnail next to the button and closes the modal.

Screenshots go outside the repo.
"""

import io
import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1472"
FIELD = "ds_afbeelding"

_LAYOUT = """() => {
  const r = e => { const b = e.getBoundingClientRect(); return {x: Math.round(b.x), right: Math.round(b.right), y: Math.round(b.y), w: Math.round(b.width)}; };
  const box = document.querySelector('#mp-ds_afbeelding');
  const paneel = box.closest('[role=dialog] > div');
  const boom = box.querySelector('details');
  const raster = box.querySelector('ul.grid');
  const eerste = raster.querySelectorAll('li');
  const rij = [...eerste].filter(li => Math.round(li.getBoundingClientRect().y) === Math.round(eerste[0].getBoundingClientRect().y)).length;
  // The widest right edge of anything in the modal: the modal can clip what
  // overflows it, so the page width alone does not show a thumbnail pushed off.
  const verst = Math.max(...[...box.querySelectorAll('*')].map(e => Math.round(e.getBoundingClientRect().right)));
  return {page: [document.documentElement.scrollWidth, innerWidth, innerHeight], paneel: r(paneel), boom: r(boom), boom_open: boom.open,
          raster: r(raster), eerste: r(eerste[0]), per_rij: rij, verst};
}"""


def _jpeg(size: tuple[int, int], colour: tuple[int, int, int]) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="JPEG")
    return buf.getvalue()


def _situation() -> tuple[int, str]:
    """Twelve design pictures with real bytes, one of them marked to be chosen."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.media.models import MediaAsset

    db = SessionLocal()
    try:
        mark = secrets.token_hex(2)
        chosen = None
        for n in range(12):
            colour = (40 + 15 * n, 90, 200 - 10 * n)
            # Not `page_image`: the CMS insert e2e takes the library's FIRST page
            # picture. A design image of no activity is offered nowhere else.
            asset = MediaAsset(
                kind="design_image",
                title=f"kiezer {mark} {n}",
                sort_order=0,
                is_active=True,
                content_type="image/jpeg",
                byte_size=100,
                width=400,
                height=300,
                data=_jpeg((400, 300), colour),
                thumbnail=_jpeg((160, 120), colour),
            )
            db.add(asset)
            db.flush()
            chosen = chosen or asset.id
        db.commit()
        return chosen, mark
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser_and_asset():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    asset_id, mark = _situation()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), asset_id, mark
        b.close()


def _open_picker(browser_and_asset, width: int):
    b, session, _asset, mark = browser_and_asset
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    page.goto("/admin/design-system")
    pagina_klaar(page)
    page.locator(f"[x-data]:has(> input[name={FIELD}]) button").first.click()
    box = page.locator(f"#mp-{FIELD}")
    box.locator("input[name=q]").fill(f"kiezer {mark}")
    box.locator(f"button[aria-label='Kies kiezer {mark} 11']").wait_for()
    pagina_klaar(page)
    return page, box


def _shot(page, name: str) -> None:
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/{name}.png")


def test_at_1440_the_tree_and_the_grid_stand_side_by_side(browser_and_asset):
    page, _box = _open_picker(browser_and_asset, 1440)
    m = page.evaluate(_LAYOUT)
    print("MEASURE 1440", m)
    _shot(page, "1440-kiezer")
    page.close()

    assert m["page"][0] <= m["page"][1], m
    assert m["boom_open"], "the tree is open next to the grid"
    assert m["boom"]["right"] <= m["raster"]["x"], f"side by side, no overlap: {m}"
    assert abs(m["boom"]["y"] - m["raster"]["y"]) < 40, f"the same row: {m}"
    assert m["per_rij"] == 5, f"five thumbnails to a row: {m}"


def test_at_390_nothing_breaks(browser_and_asset):
    page, _box = _open_picker(browser_and_asset, 390)
    m = page.evaluate(_LAYOUT)
    print("MEASURE 390", m)
    _shot(page, "390-kiezer")
    page.close()

    assert m["paneel"]["x"] >= 0 and m["paneel"]["right"] <= m["page"][1], f"the panel fits: {m}"
    assert m["verst"] <= m["page"][1], f"something in the modal sticks out: {m}"
    assert not m["boom_open"], "the tree is folded on a phone"
    assert m["eerste"]["y"] + m["eerste"]["w"] <= m["page"][2], (
        f"the grid starts on the first screen: {m}"
    )


def test_choosing_sets_the_field_shows_the_thumbnail_and_closes(browser_and_asset):
    _b, _s, asset_id, mark = browser_and_asset
    page, box = _open_picker(browser_and_asset, 1440)
    box.locator(f"button[aria-label='Kies kiezer {mark} 0']").click()
    box.wait_for(state="hidden")
    state = page.evaluate(
        f"""() => {{
      const veld = document.querySelector('input[name={FIELD}]');
      const img = veld.parentElement.querySelector('img');
      return {{value: veld.value, thumb: img.getAttribute('src'), shown: img.checkVisibility(),
               modal: document.querySelector('#mp-{FIELD}').checkVisibility(), natural: img.naturalWidth}};
    }}"""
    )
    print("CHOSEN", state)
    _shot(page, "1440-gekozen")
    page.close()

    assert state["value"] == str(asset_id)
    assert state["thumb"] == f"/api/v1/media/{asset_id}/thumb"
    assert state["shown"], "the chosen thumbnail shows next to the button"
    assert not state["modal"], "the modal closed"

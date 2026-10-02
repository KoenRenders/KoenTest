"""E2E: the CMS page places an album photo from the kit's picker (CR-15 C6 test 2, #1474).

In a browser, on a CMS page: open "Afbeelding", find an album photo of the Sint
in the picker by searching for it, choose it — the alt is its title — insert,
save. Measured:

- the number of media rows before and after: equal (a reference, no copy);
- the page shows the photo, and it loads (`naturalWidth`);
- the dialog at 1 440 and 390 px: its panel fits the viewport, the picker's
  thumbnails show, and nothing in the dialog sticks out.

Screenshots go outside the repo.
"""

import io
import os
import re
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Paginascherm, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1474"

_DIALOG = """() => {
  const box = document.querySelector('#mp-cp-beeld');
  const paneel = box.closest('[role=dialog] > div');
  const r = e => { const b = e.getBoundingClientRect(); return {x: Math.round(b.x), right: Math.round(b.right), y: Math.round(b.y), w: Math.round(b.width)}; };
  const duim = box.querySelector('button[data-url]');
  const verst = Math.max(...[...paneel.querySelectorAll('*')].filter(e => e.checkVisibility()).map(e => Math.round(e.getBoundingClientRect().right)));
  return {page: [document.documentElement.scrollWidth, innerWidth], paneel: r(paneel), duim: duim ? r(duim) : null, verst};
}"""


def _media_rows() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.media.models import MediaAsset

    db = SessionLocal()
    try:
        return db.query(MediaAsset).execution_options(include_all_tenants=True).count()
    finally:
        db.close()


def _album_photo() -> tuple[int, str]:
    """An album photo with real bytes, so the browser really loads it."""
    from PIL import Image

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.media.models import MediaAsset

    buf = io.BytesIO()
    Image.new("RGB", (320, 200), (180, 60, 40)).save(buf, format="PNG")
    png = buf.getvalue()
    title = f"Sint album {secrets.token_hex(2)}"
    db = SessionLocal()
    try:
        asset = MediaAsset(
            kind="activity_photo",
            title=title,
            data=png,
            content_type="image/png",
            thumbnail=png,
            thumb_content_type="image/png",
            width=320,
            height=200,
            byte_size=len(png),
            sort_order=0,
            is_active=True,
        )
        db.add(asset)
        db.commit()
        return asset.id, title
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser_and_photo():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    photo = _album_photo()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), photo
        b.close()


def _open_dialog(browser_and_photo, width: int):
    b, session, (photo_id, title) = browser_and_photo
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    scherm = Paginascherm(page).open_eerste()
    if scherm is None:
        pytest.fail("e2e-seed geladen maar: geen cms-pagina")
    page.get_by_role("button", name="Afbeelding").first.click()
    dialoog = page.get_by_role("dialog")
    expect(dialoog).to_be_visible()
    # The picker loads when the dialog opens; type only once htmx has taken it
    # in — typed sooner, the input event fires before anything listens.
    dialoog.locator("#mp-cp-beeld button[data-url]").first.wait_for()
    pagina_klaar(page)
    dialoog.locator("#mp-cp-beeld input[name=q]").fill(title)
    keuze = dialoog.locator(f"button[data-id='{photo_id}']")
    keuze.wait_for()
    # The search ran: only the album photo is left (a failed search kept the
    # whole list, the photo included).
    expect(dialoog.locator("#mp-cp-beeld button[data-url]")).to_have_count(1)
    pagina_klaar(page)
    return page, scherm, dialoog, keuze


def _shot(page, name: str) -> None:
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/{name}.png")


def test_an_album_photo_is_placed_as_a_reference(browser_and_photo):
    """C6 test 2."""
    _b, _s, (photo_id, title) = browser_and_photo
    page, scherm, dialoog, keuze = _open_dialog(browser_and_photo, 1440)
    before = _media_rows()

    keuze.click()
    assert dialoog.locator("#cp-alt").input_value() == title, (
        "the alt starts at the picture's title"
    )
    expect(dialoog.locator("img[data-cp-gekozen]")).to_be_visible()
    dialoog.get_by_role("button", name="Invoegen").click()
    assert f"/api/v1/media/{photo_id}" in scherm.editorinhoud()
    scherm.opslaan()
    after = _media_rows()

    page_id = re.search(r"/admin/paginas/(\d+)", page.url).group(1)
    page.goto(f"/admin/paginas/{page_id}/voorbeeld")
    beeld = page.locator(f"img[src='/api/v1/media/{photo_id}']")
    expect(beeld).to_have_count(1)
    loaded = page.evaluate("el => el.complete && el.naturalWidth", beeld.element_handle())
    print("MEASURE rows", before, after, "naturalWidth", loaded)
    page.close()

    assert after == before, "placing a picture stored a copy"
    assert loaded == 320, "the photo is on the page but does not load"


@pytest.mark.parametrize("width", [1440, 390])
def test_the_dialog_fits(browser_and_photo, width):
    page, _scherm, _dialoog, _keuze = _open_dialog(browser_and_photo, width)
    m = page.evaluate(_DIALOG)
    print("MEASURE", width, m)
    _shot(page, f"{width}-dialoog")
    page.close()

    assert m["paneel"]["x"] >= 0 and m["paneel"]["right"] <= width, f"the panel fits: {m}"
    assert m["verst"] <= m["paneel"]["right"], f"something sticks out of the dialog: {m}"
    assert m["duim"] is not None, "the picker shows its thumbnails"

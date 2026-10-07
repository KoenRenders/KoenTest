"""E2E: the album's lightbox and photo grid as components (#1665; CR-11 pilot C,
C3 — Z5, Z6; end state §2.7).

- close, previous and next are the kit's 24 px icons in real buttons of
  44 × 44 px with Dutch names (they were the characters ✕ ‹ ›);
- the focus goes to Close on opening, stays inside on Tab and Shift+Tab, and
  returns to the thumbnail that opened the lightbox; the page keeps its scroll
  position;
- Escape, the ground and Close close; a click on the photo does not; the arrow
  keys step, and at either end the arrow that leads nowhere is hidden;
- the thumbs-up has a hit area of 44 × 44 px around its pill of 20 px, which
  stays where it stood, and a click on it opens no photo;
- the photo stands where and as large as it stood: uncropped, at most 90 % of
  the window's height and the window's width less 16 px on either side.

An album of three photos of 640 × 480 is made for this file and removed again.

Red against C2 (`5d6a078f`, measured): the controls are the characters ✕ ‹ › —
no `svg` — the close control 25 × 30 px and an arrow 42 × 96 px; after opening
the focus is not in the lightbox (the thumbnail keeps it) and the first three
Tabs walk the page behind it; the thumbs-up has no hit area but its pill of
42 × 20 px.
"""

import os
import sys
from datetime import date, timedelta
from io import BytesIO

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402


def _png(colour: tuple[int, int, int], size: tuple[int, int] = (640, 480)) -> bytes:
    from PIL import Image

    out = BytesIO()
    Image.new("RGB", size, colour).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture(scope="module")
def album():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate
    from app.domains.media.api import MediaAsset

    db = SessionLocal()
    made: dict = {"photos": []}
    try:
        activity = Activity(name="Meting lichtbak 1665")
        db.add(activity)
        db.flush()
        day = ActivityDate(activity_id=activity.id, start_date=date.today() - timedelta(days=50))
        db.add(day)
        for order, colour in enumerate(((37, 78, 115), (238, 193, 94), (25, 95, 157))):
            photo = MediaAsset(
                kind="activity_photo",
                activity_id=activity.id,
                title=f"Meting foto {order + 1}",
                # The third is larger than any window: the lightbox must cap it.
                data=_png(colour, (1600, 1200) if order == 2 else (640, 480)),
                content_type="image/png",
                thumbnail=_png(colour, (320, 240)),
                thumb_content_type="image/png",
                width=640,
                height=480,
                byte_size=10,
                sort_order=order,
                is_active=True,
            )
            db.add(photo)
            db.flush()
            made["photos"].append(photo.id)
        db.commit()
        made.update(activity=activity.id, day=day.id)
    finally:
        db.close()

    yield made

    db = SessionLocal()
    try:
        from app.domains.media.api import MediaThumbsUp

        db.query(MediaThumbsUp).filter(
            MediaThumbsUp.asset_id.in_(made["photos"])
        ).execution_options(include_all_tenants=True).delete(synchronize_session=False)
        for model, ids in (
            (MediaAsset, made["photos"]),
            (ActivityDate, [made["day"]]),
            (Activity, [made["activity"]]),
        ):
            db.query(model).filter(model.id.in_(ids)).execution_options(
                include_all_tenants=True, include_deleted=True
            ).delete(synchronize_session=False)
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


def _album(browser, album, width: int, height: int):
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    page.goto(f"/activiteiten/{album['activity']}/fotos")
    pagina_klaar(page)
    return page


def _open(page, index: int = 0) -> None:
    page.locator("[data-photo-open]").nth(index).click()
    page.locator("[data-lightbox]").wait_for(state="visible")
    page.wait_for_function(
        "() => { const i = document.querySelector('[data-lightbox-photo]'); return i.complete && i.naturalWidth > 0; }"
    )


FOCUS = """() => { const a = document.activeElement;
  return a.hasAttribute('data-lightbox-close') ? 'close' : a.hasAttribute('data-lightbox-previous') ? 'previous'
       : a.hasAttribute('data-lightbox-next') ? 'next' : a.hasAttribute('data-photo-open') ? 'thumbnail'
       : a.tagName.toLowerCase(); }"""
SHOWN = """() => { const i = document.querySelector('[data-lightbox-photo]');
  return document.querySelector('[data-lightbox]').checkVisibility() ? i.getAttribute('src') : null; }"""
CONTROLS = """() => Object.fromEntries(['close', 'previous', 'next'].map(n => {
  const b = document.querySelector(`[data-lightbox-${n}]`), r = b.getBoundingClientRect(), g = b.querySelector('svg');
  return [n, {tag: b.tagName, shown: b.checkVisibility(), box: [Math.round(r.width), Math.round(r.height)],
              icon: g ? [Math.round(g.getBoundingClientRect().width), Math.round(g.getBoundingClientRect().height)] : null,
              name: b.getAttribute('aria-label'), text: b.textContent.trim()}]; }))"""
PHOTO = """() => { const r = document.querySelector('[data-lightbox-photo]').getBoundingClientRect();
  return [r.width, r.height, r.left, r.top]; }"""


@pytest.mark.parametrize(("width", "height"), [(390, 844), (1440, 900)])
def test_the_three_controls_are_icon_buttons_of_44_px(browser, album, width, height):
    page = _album(browser, album, width, height)
    _open(page, 1)  # the middle photo: both arrows show
    _arrows(page, True, True)
    controls = page.evaluate(CONTROLS)
    print("MEASURE lightbox controls", width, controls)
    names = {"close": "Sluiten", "previous": "Vorige foto", "next": "Volgende foto"}
    for key, control in controls.items():
        assert control["tag"] == "BUTTON" and control["shown"], f"{key}: {control}"
        assert control["box"] == [44, 44], f"{key} is {control['box']} px"
        assert control["icon"] == [24, 24], f"{key}: the icon is {control['icon']}"
        assert control["name"] == names[key] and control["text"] == "", f"{key}: {control}"
    page.close()


@pytest.mark.parametrize(
    ("width", "height", "index", "box"),
    [
        # 640 × 480: capped by the width on a phone (92 % of it), its own size on a desktop.
        (390, 844, 0, (358.8, 269.1, 15.6, 287.45)),
        (1440, 900, 0, (640, 480, 400, 210)),
        # 1 600 × 1 200: capped by 90 % of the window's height on a desktop.
        (390, 844, 2, (358.8, 269.1, 15.6, 287.45)),
        (1440, 900, 2, (1080, 810, 180, 45)),
    ],
)
def test_the_photo_stands_where_and_as_large_as_it_stood(browser, album, width, height, index, box):
    """Uncropped and centred, at most 90 % of the window's height and 92 % of its
    width. The first two rows are what C2 measured for the same picture
    (358.8 × 269.1 at 15.6, 287.5 and 640 × 480 at 400, 210)."""
    page = _album(browser, album, width, height)
    _open(page, index)
    measured = page.evaluate(PHOTO)
    print("MEASURE lightbox photo", width, measured)
    assert all(abs(a - b) <= 0.5 for a, b in zip(measured, box)), f"@{width}: {measured}, was {box}"
    page.close()


def test_the_focus_goes_to_close_stays_inside_and_returns_to_the_thumbnail(browser, album):
    page = _album(browser, album, 1440, 500)  # a low window: the page scrolls
    page.evaluate("() => scrollTo(0, 120)")
    before = page.evaluate("() => scrollY")
    assert before > 0, "the page does not scroll — the scroll position would prove nothing"
    _open(page, 1)
    # Alpine sets the focus a tick after the lightbox shows: wait for it, never read at once.
    page.wait_for_function(
        "() => document.activeElement.hasAttribute('data-lightbox-close')", timeout=3000
    )
    assert page.evaluate(FOCUS) == "close"
    # Tab walks the three buttons and comes round; Shift+Tab walks back.
    order = []
    for _ in range(4):
        page.keyboard.press("Tab")
        order.append(page.evaluate(FOCUS))
    assert order == ["previous", "next", "close", "previous"], order
    back = []
    for _ in range(3):
        page.keyboard.press("Shift+Tab")
        back.append(page.evaluate(FOCUS))
    assert back == ["close", "next", "previous"], back
    print("MEASURE lightbox focus order", ["close", *order], back)
    page.keyboard.press("Escape")
    page.locator("[data-lightbox]").wait_for(state="hidden")
    page.wait_for_function(
        "() => document.activeElement.hasAttribute('data-photo-open')", timeout=3000
    )
    assert page.evaluate(FOCUS) == "thumbnail"
    assert (
        page.evaluate(
            "() => [...document.querySelectorAll('[data-photo-open]')].indexOf(document.activeElement)"
        )
        == 1
    ), "the focus is not on the thumbnail that opened the lightbox"
    assert page.evaluate("() => scrollY") == before, "the page jumped"
    page.close()


def _arrows(page, previous: bool, following: bool) -> None:
    """Wait until the two arrows show as asked: Alpine's `x-show` SHOWS on a
    timeout, a moment after the state changed."""
    page.wait_for_function(
        """([p, n]) => document.querySelector('[data-lightbox-previous]').checkVisibility() === p
                     && document.querySelector('[data-lightbox-next]').checkVisibility() === n""",
        arg=[previous, following],
        timeout=3000,
    )


def test_the_arrow_keys_step_and_the_ends_hide_the_arrow_that_leads_nowhere(browser, album):
    page = _album(browser, album, 1440, 900)
    _open(page, 0)
    first = page.evaluate(SHOWN)
    _arrows(page, False, True)
    page.keyboard.press("ArrowLeft")
    assert page.evaluate(SHOWN) == first, "the lightbox ran round from the first photo"
    page.keyboard.press("ArrowRight")
    second = page.evaluate(SHOWN)
    assert second != first
    _arrows(page, True, True)
    page.keyboard.press("ArrowRight")
    third = page.evaluate(SHOWN)
    assert third not in (first, second)
    _arrows(page, True, False)
    page.keyboard.press("ArrowRight")
    assert page.evaluate(SHOWN) == third, "the lightbox ran round from the last photo"
    # The button that gets hidden under the focus hands it to Close, never to the page.
    page.keyboard.press("ArrowLeft")
    _arrows(page, True, True)
    page.locator("[data-lightbox-next]").focus()
    page.keyboard.press("Enter")
    _arrows(page, True, False)
    assert page.evaluate(SHOWN) == third
    page.wait_for_function(
        "() => document.activeElement.hasAttribute('data-lightbox-close')", timeout=3000
    )
    page.close()


def test_close_the_ground_and_escape_close_and_the_photo_does_not(browser, album):
    page = _album(browser, album, 1440, 900)
    box = page.locator("[data-lightbox]")
    _open(page, 1)
    page.locator("[data-lightbox-photo]").click()
    assert box.is_visible(), "a click on the photo closed the lightbox"
    page.locator("[data-lightbox-close]").click()
    box.wait_for(state="hidden")
    _open(page, 1)
    page.mouse.click(20, 450)  # the dark ground, beside the photo
    box.wait_for(state="hidden")
    _open(page, 1)
    page.keyboard.press("Escape")
    box.wait_for(state="hidden")
    page.close()


THUMB = """() => { const b = document.querySelector('[data-photo] button[aria-pressed]'), r = b.getBoundingClientRect();
  const tile = b.closest('[data-photo]').getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const hit = (dx, dy) => { const e = document.elementFromPoint(cx + dx, cy + dy); return !!e && (e === b || b.contains(e)); };
  const s = getComputedStyle(b, '::before');
  return {pill: [Math.round(r.width), Math.round(r.height)], from_tile: [Math.round(tile.right - r.right), Math.round(tile.bottom - r.bottom)],
          area: [s.width, s.height], left: hit(-21, 0), up: hit(0, -21), far_left: hit(-24, 0), far_up: hit(0, -24)}; }"""


@pytest.mark.parametrize(("width", "height"), [(390, 844), (1440, 900)])
def test_the_thumbs_up_has_a_hit_area_of_44_px_and_opens_no_photo(browser, album, width, height):
    page = _album(browser, album, width, height)
    m = page.evaluate(THUMB)
    print("MEASURE thumbs-up", width, m)
    # The visible pill: 20 px high, 6 px from the thumbnail's right edge and 9 px
    # from its bottom edge — where C2 had it (measured there: 42 × 20 at 6, 9).
    assert m["pill"][1] == 20 and m["from_tile"] == [6, 9], m
    assert m["area"] == ["44px", "44px"], m
    assert m["left"] and m["up"] and not m["far_left"] and not m["far_up"], m
    # In the hit area, above the pill: the thumbs-up answers and no photo opens.
    button = page.locator("[data-photo] button[aria-pressed]").first
    count = int(button.inner_text().strip())
    box = button.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] - 8)
    page.wait_for_function(
        "() => document.querySelector('[data-photo] button[aria-pressed]').getAttribute('aria-pressed') === 'true'"
    )
    assert not page.locator("[data-lightbox]").is_visible(), "the thumbs-up opened a photo"
    after = int(page.locator("[data-photo] button[aria-pressed]").first.inner_text().strip())
    assert after == count + 1, f"the thumbs-up went from {count} to {after}"
    page.close()

"""E2E: the album card moves, stands still and links (CR-32 phase 6, AC8).

Three albums of four photos, every two seconds: the card shows the first album's
cover, moves on photo by photo, and a click lands on the album it shows; with the
browser's reduced motion it stands still; in the author's preview it never moves.

Broken on purpose (15 October 2026): the `setInterval` of the macro taken out →
the card never moves; the reduced-motion guard taken out → it moves for a
visitor who asked for none.
"""

import io
import os
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

COLOURS = [(37, 78, 115), (238, 193, 94), (120, 160, 120), (180, 90, 90)]


@pytest.fixture(scope="module")
def setup():
    from PIL import Image

    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.models import Activity, ActivityDate
    from app.domains.auth.api import make_session_value
    from app.domains.cms.api import CmsPage, publish, save_document
    from app.domains.cms.service import create_page
    from app.domains.media.models import MediaAsset
    from app.schemas.cms import CmsPageCreate
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    activity_ids = []
    for index, year in enumerate((2022, 2021, 2020)):
        activity = Activity(name=f"Kaartfeest {tag} {index}", location="Voorbeeldplein 1")
        db.add(activity)
        db.flush()
        activity_ids.append(activity.id)
        db.add(ActivityDate(activity_id=activity.id, start_date=date(year, 6, 1)))
        for order in range(4):
            buf = io.BytesIO()
            Image.new("RGB", (640, 480), COLOURS[(order + index) % 4]).save(buf, "PNG")
            png = buf.getvalue()
            db.add(
                MediaAsset(
                    kind="activity_photo",
                    activity_id=activity.id,
                    title=f"Foto {order}",
                    data=png,
                    content_type="image/png",
                    thumbnail=png,
                    thumb_content_type="image/png",
                    width=640,
                    height=480,
                    byte_size=len(png),
                    sort_order=order,
                    is_active=True,
                )
            )
    page = create_page(
        db, CmsPageCreate(title="Albumkaart", slug=f"kaart-{tag}", show_in_nav=False)
    )
    save_document(
        db,
        page.id,
        {
            "type": "doc",
            "content": [{"type": "albums", "attrs": {"albums": 3, "photos": 4, "interval": 2}}],
        },
    )
    publish(db, page.id)
    db.commit()
    page_id, slug = page.id, page.slug
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, page_id, slug, activity_ids, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()
    c = SessionLocal()
    try:
        c.query(CmsPage).filter(CmsPage.id == page_id).delete()
        c.query(MediaAsset).filter(MediaAsset.activity_id.in_(activity_ids)).delete(
            synchronize_session=False
        )
        c.query(ActivityDate).filter(ActivityDate.activity_id.in_(activity_ids)).delete(
            synchronize_session=False
        )
        c.query(Activity).filter(Activity.id.in_(activity_ids)).delete(synchronize_session=False)
        c.commit()
    finally:
        c.close()


_STATE = """() => { const c = document.querySelector('[data-photo-card]');
  return {href: c.getAttribute('href'), src: c.querySelector('img').getAttribute('src'),
          name: c.querySelector('.font-semibold').innerText,
          cards: document.querySelectorAll('[data-photo-card]').length}; }"""


def test_the_card_moves_photo_by_photo_and_a_click_opens_the_album_it_shows(setup):
    b, _id, slug, ids, _session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        page.goto(f"/{slug}")
        pagina_klaar(page)
        first = page.evaluate(_STATE)
        assert first["cards"] == 1 and first["name"].endswith(" 0"), first
        page.wait_for_function(
            "(src) => document.querySelector('[data-photo-card] img').getAttribute('src') !== src",
            arg=first["src"],
            timeout=6000,
        )
        second = page.evaluate(_STATE)
        assert second["src"] != first["src"] and second["href"] == first["href"], (first, second)
        # Four photos of the first album, then the second album.
        page.wait_for_function(
            "(name) => document.querySelector('[data-photo-card] .font-semibold').innerText !== name",
            arg=first["name"],
            timeout=12000,
        )
        moved = page.evaluate(_STATE)
        assert moved["name"].endswith(" 1") and moved["href"] != first["href"], moved
        before_click = page.evaluate(_STATE)
        page.locator("[data-photo-card]").click()
        page.wait_for_url("**/activiteiten/**", timeout=8000)
        assert page.url.endswith(before_click["href"]) or page.url.endswith(moved["href"]), (
            f"the click did not open the album the card showed: {page.url} against {moved}"
        )
    finally:
        page.close()


def _after_five_seconds(page, path):
    """Load `path` on a fake clock and let five seconds go by — no waiting on the real
    clock (the gate of #997): the timers of the page run when the test says so."""
    page.clock.install()
    page.goto(path)
    pagina_klaar(page)
    first = page.evaluate(_STATE)
    page.clock.run_for(5000)
    return first, page.evaluate(_STATE)


def test_the_fake_clock_does_move_the_card(setup):
    """The control of the two tests below: on the same fake clock, with motion
    allowed, five seconds move the card — so "it did not move" means something."""
    b, _id, slug, _ids, _session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        first, later = _after_five_seconds(page, f"/{slug}")
        assert later["src"] != first["src"], (first, later)
    finally:
        page.close()


def test_with_reduced_motion_the_card_stands_still(setup):
    b, _id, slug, _ids, _session = setup
    context = b.new_context(
        base_url=BASE, reduced_motion="reduce", viewport={"width": 390, "height": 844}
    )
    page = context.new_page()
    try:
        first, later = _after_five_seconds(page, f"/{slug}")
        assert later == first, "the card moved for a visitor who asked for stillness"
    finally:
        context.close()


def test_in_the_preview_the_card_stands_still(setup):
    b, page_id, _slug, _ids, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        login_met_sessie(page, session)
        first, later = _after_five_seconds(page, f"/admin/paginas/{page_id}/voorbeeld")
        assert later == first
    finally:
        page.close()

"""E2E: the gallery block, built through the dialog and measured (CR-32 phase 4,
R20, AC11).

The walk: the author inserts a gallery, chooses an album in the dialog, saves and
publishes; the site shows a grid of that album's photos, each opening the photo.
The measurement: two photos across at 390 px and more at 1 280 px, every photo
at the same size, the document never wider than the viewport.

Broken on purpose (15 October 2026): the dialog's `raak-gallery-apply` dispatch
taken out → the walk never inserts a block; the grid rule taken out of the
stylesheet → one photo per row at 1 280 px and the row test fails.
"""

import os
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

EDITOR = "#cp-document"
_MENU = f"{EDITOR} details.de-menu-insert"
PHOTOS = 6


@pytest.fixture(scope="module")
def setup():
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
    activity = Activity(name=f"Galerijfeest {tag}", location="Voorbeeldplein 1")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2020, 6, 1)))
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    for order in range(PHOTOS):
        db.add(
            MediaAsset(
                kind="activity_photo",
                activity_id=activity.id,
                title=f"Foto {order + 1}",
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
    walk = create_page(db, CmsPageCreate(title="Galerijwandeling", slug=f"galerij-{tag}"))
    save_document(
        db,
        walk.id,
        {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Foto's."}]}],
        },
    )
    publish(db, walk.id)
    measured = create_page(db, CmsPageCreate(title="Galerijrooster", slug=f"rooster-{tag}"))
    save_document(
        db,
        measured.id,
        {"type": "doc", "content": [{"type": "gallery", "attrs": {"activity_id": activity.id}}]},
    )
    publish(db, measured.id)
    db.commit()
    ids = [walk.id, measured.id]
    info = (walk.id, walk.slug, measured.slug, activity.name, activity.id)
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield (b, *info, make_session_value(SEEDED_ADMIN_EMAIL))
        b.close()
    cleanup = SessionLocal()
    try:
        cleanup.query(CmsPage).filter(CmsPage.id.in_(ids)).delete(synchronize_session=False)
        # The album goes too: while it stands, every editor's menu offers a gallery.
        cleanup.query(MediaAsset).filter(MediaAsset.activity_id == info[4]).delete()
        cleanup.query(ActivityDate).filter(ActivityDate.activity_id == info[4]).delete()
        cleanup.query(Activity).filter(Activity.id == info[4]).delete()
        cleanup.commit()
    finally:
        cleanup.close()


def test_the_author_makes_a_gallery_through_the_dialog(setup):
    b, page_id, slug, _measured, album_name, _activity, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap")
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Galerij").click()
        page.wait_for_selector("[data-gallery-album]", state="visible")
        page.select_option("[data-gallery-album]", label=f"{album_name} (2020)")
        page.locator("[data-gallery-apply]").click()
        page.wait_for_selector(f"{EDITOR} .tiptap .de-gallery")
        assert album_name in page.locator(f"{EDITOR} .tiptap .de-gallery").inner_text()

        page.locator("[data-action-bar] button[data-form-save]").click()
        page.wait_for_url(f"**/admin/paginas/{page_id}*opgeslagen=1*", timeout=15000)
        pagina_klaar(page)
        page.locator("button", has_text="Publiceren").click()
        page.wait_for_function(
            "() => document.querySelector('[data-record-head]') && "
            "!document.querySelector('[data-record-head]').textContent.includes('Concept gewijzigd')",
            timeout=15000,
        )
        page.goto(f"/{slug}")
        pagina_klaar(page)
        assert page.locator(".cms-page .prose-gallery a").count() == PHOTOS
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


_GRID = """() => { const g = document.querySelector('.cms-page .prose-gallery');
  const r = g.getBoundingClientRect();
  const items = [...g.querySelectorAll('a')].map(a => { const b = a.getBoundingClientRect();
    return {left: Math.round(b.left), top: Math.round(b.top), width: Math.round(b.width), height: Math.round(b.height)}; });
  return {box: {left: Math.round(r.left), width: Math.round(r.width)}, items,
          href: g.querySelector('a').getAttribute('href'),
          doc: document.documentElement.scrollWidth, vw: innerWidth}; }"""


@pytest.mark.parametrize(("width", "columns"), [(1280, 5), (390, 2)])
def test_the_photos_stand_in_a_grid_and_open_the_photo(setup, width, columns):
    b, _id, _slug, measured, _name, _activity, _session = setup
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        page.goto(f"/{measured}")
        pagina_klaar(page)
        m = page.evaluate(_GRID)
        print("MEASURE gallery", width, m)
        assert len(m["items"]) == PHOTOS
        first_row = [i for i in m["items"] if i["top"] == m["items"][0]["top"]]
        assert len(first_row) == min(columns, PHOTOS), (width, first_row)
        assert len({(i["width"], i["height"]) for i in m["items"]}) == 1, "photos differ in size"
        assert m["href"].startswith("/api/v1/media/") and not m["href"].endswith("/thumb")
        assert m["doc"] == m["vw"], "the page scrolls sideways"
        assert m["box"]["left"] >= 0 and m["box"]["left"] + m["box"]["width"] <= width
    finally:
        page.close()

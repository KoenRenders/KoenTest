"""E2E: the activities and the album card in the columns of a page (CR-32 #2101).

The walk: the author puts the cursor in a column, chooses the ratio "Breed – smal" and
inserts the activities there and the album card in the other column; the site draws the
two columns outside the prose, three to two at 1 100 px and stacked at 390 px.

Broken on purpose (18 October 2026): the editor's `dataBlockPos` taken out → the block
lands at the document's end, not in the column; the `prose-columns--wide-narrow` rule
taken out of the stylesheet → the two columns are as wide as each other; the page template
drawing a cell's data block inside the prose → the structural assertion fails.
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

EDITOR = "#cp-document"
_MENU = f"{EDITOR} details.de-menu-insert"


def _par(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


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
    # One upcoming activity for the left column, one past album for the right one.
    for name, year in ((f"Kolomfeest {tag} komt", 2031), (f"Kolomfeest {tag} was", 2020)):
        activity = Activity(name=name, location="Voorbeeldplein 1")
        db.add(activity)
        db.flush()
        activity_ids.append(activity.id)
        db.add(ActivityDate(activity_id=activity.id, start_date=date(year, 6, 1)))
    for order in range(3):
        buf = io.BytesIO()
        Image.new("RGB", (640, 480), (37 + order * 40, 78, 115)).save(buf, "PNG")
        png = buf.getvalue()
        db.add(
            MediaAsset(
                kind="activity_photo",
                activity_id=activity_ids[1],
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
    walk = create_page(db, CmsPageCreate(title="Kolommenwandeling", slug=f"kolwand-{tag}"))
    save_document(
        db,
        walk.id,
        {
            "type": "doc",
            "content": [
                {
                    "type": "columns",
                    "attrs": {"align": "top"},
                    "content": [
                        {"type": "column", "content": [_par("Links.")]},
                        {"type": "column", "content": [_par("Rechts.")]},
                    ],
                },
                _par("Buiten de kolommen."),
            ],
        },
    )
    publish(db, walk.id)
    db.commit()
    walk_id, walk_slug = walk.id, walk.slug
    db.close()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, walk_id, walk_slug, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()
    cleanup = SessionLocal()
    try:
        cleanup.query(CmsPage).filter(CmsPage.id == walk_id).delete()
        cleanup.query(MediaAsset).filter(MediaAsset.activity_id.in_(activity_ids)).delete(
            synchronize_session=False
        )
        cleanup.query(ActivityDate).filter(ActivityDate.activity_id.in_(activity_ids)).delete(
            synchronize_session=False
        )
        cleanup.query(Activity).filter(Activity.id.in_(activity_ids)).delete(
            synchronize_session=False
        )
        cleanup.commit()
    finally:
        cleanup.close()


_MEASURE = """() => {
  const box = (e) => { const b = e.getBoundingClientRect(); return {x: b.x, y: b.y, w: b.width, h: b.height}; };
  const grid = document.querySelector('[data-page-columns]');
  const cols = [...grid.querySelectorAll(':scope > .prose-column')];
  const title = document.querySelector('.page-data [data-card-title]');
  return {
    grid: box(grid),
    left: box(cols[0]),
    right: box(cols[1]),
    leftActivities: !!cols[0].querySelector('[data-card-title]'),
    rightCard: !!cols[1].querySelector('[data-photo-card]'),
    outsideProse: [...grid.querySelectorAll('.page-data')].every(e => !e.closest('.prose-raak')),
    gridOutsideProse: !grid.closest('.prose-raak'),
    titleUnderline: getComputedStyle(title).textDecorationLine,
    docWidth: document.documentElement.scrollWidth,
    vw: innerWidth,
  };
}"""


def test_the_author_puts_the_activities_and_the_album_card_in_the_columns(setup):
    b, page_id, slug, session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1100, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto(f"/admin/paginas/{page_id}")
        pagina_klaar(page)
        page.wait_for_selector(f"{EDITOR} .tiptap .prose-column")
        ratio = page.locator(f"{EDITOR} select.de-ratio")
        page.click(f"{EDITOR} .tiptap > p")
        ratio.wait_for(state="hidden", timeout=3000)  # outside the columns it stays away
        page.click(f"{EDITOR} .tiptap .prose-column >> nth=0")
        ratio.wait_for(state="visible", timeout=3000)
        ratio.select_option("wide-narrow")
        page.wait_for_selector(f"{EDITOR} .tiptap .prose-columns--wide-narrow")
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Activiteiten").click()
        page.wait_for_selector(f"{EDITOR} .tiptap .prose-column >> nth=0 >> .de-gallery")
        page.click(f"{EDITOR} .tiptap .prose-column >> nth=1")
        page.locator(f"{_MENU} summary").click()
        page.locator(f"{_MENU} button", has_text="Albumkaart").click()
        page.wait_for_selector(f"{EDITOR} .tiptap .prose-column >> nth=1 >> .de-gallery")
        assert page.locator(f"{EDITOR} .tiptap > .de-gallery").count() == 0, (
            "the block landed at the document's end"
        )
        page.locator("[data-action-bar] button[data-form-save]").click()
        page.wait_for_url(f"**/admin/paginas/{page_id}*opgeslagen=1*", timeout=15000)
        pagina_klaar(page)
        page.locator("button", has_text="Publiceren").click()
        page.wait_for_function(
            "() => document.querySelector('[data-record-head]') && "
            "!document.querySelector('[data-record-head]').textContent.includes('Concept gewijzigd')",
            timeout=15000,
        )
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()


def test_the_columns_stand_three_to_two_outside_the_prose_and_stack_on_a_phone(setup):
    b, _id, slug, _session = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1100, "height": 900})
    try:
        page.goto(f"/{slug}")
        pagina_klaar(page)
        wide = page.evaluate(_MEASURE)
        print("MEASURE columns 1100", wide)
        assert wide["leftActivities"] and wide["rightCard"], wide
        assert wide["outsideProse"] and wide["gridOutsideProse"], wide
        assert wide["titleUnderline"] == "none", "an activity title carries the prose's link style"
        assert abs(wide["left"]["w"] / wide["right"]["w"] - 1.5) < 0.03, wide
        assert abs(wide["left"]["w"] / (wide["grid"]["w"] - 32) - 0.6) < 0.01, wide
        assert wide["right"]["x"] > wide["left"]["x"] + wide["left"]["w"], "not side by side"
        phone = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        try:
            phone.goto(f"/{slug}")
            pagina_klaar(phone)
            narrow = phone.evaluate(_MEASURE)
            print("MEASURE columns 390", narrow)
            assert narrow["right"]["y"] >= narrow["left"]["y"] + narrow["left"]["h"], (
                "the album card does not stand under the activities"
            )
            assert narrow["left"]["x"] == narrow["right"]["x"]
            assert narrow["docWidth"] == narrow["vw"], "the page scrolls sideways"
            if os.environ.get("E2E_PRINT_DIR"):
                phone.screenshot(
                    path=os.path.join(os.environ["E2E_PRINT_DIR"], "kolommen-390.png"),
                    full_page=False,
                )
        finally:
            phone.close()
        if os.environ.get("E2E_PRINT_DIR"):
            page.screenshot(path=os.path.join(os.environ["E2E_PRINT_DIR"], "kolommen-1100.png"))
    finally:
        page.close()

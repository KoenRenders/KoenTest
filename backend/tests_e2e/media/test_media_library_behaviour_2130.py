"""E2E #2130: the media library on the kit keeps its behaviour — section 4 of
the concept of CR-11 round 3b, walked in a browser (Koen, 18 October 2026: "het
gedrag blijft identiek").

- "+ Uploaden" carries the chosen branch, also after a click in the tree or a
  search (#1138), and the upload form starts on that kind, activity and tag;
- after an upload of several files you are back on the same branch;
- the filter state stands in the address (tree and search);
- the order arrows stand only with a branch chosen, not in "Alles";
- a refused action shows its reason above the cards;
- new: a picture's record remembers the list (branch, year, search) for its way
  back and after saving.
"""

from __future__ import annotations

import io
import os
import re
import secrets
import sys
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, login_met_sessie, pagina_klaar  # noqa: E402

MARK = secrets.token_hex(3)


def _png(color=(30, 120, 60)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def situation() -> dict:
    """An activity of 2027 with two photos, and a tag with one picture."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate
    from app.domains.media.api import MediaAsset, MediaKind, create_tag, set_asset_tags

    db = SessionLocal()
    activity = Activity(name=f"Herfstwandeling {MARK}", location="Miloheem")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2027, 10, 1)))
    data = _png()
    photos = []
    for n, title in enumerate((f"Bos {MARK}", f"Beek {MARK}")):
        photo = MediaAsset(
            kind=MediaKind.ACTIVITY_PHOTO,
            activity_id=activity.id,
            title=title,
            data=data,
            content_type="image/png",
            thumbnail=data,
            thumb_content_type="image/png",
            width=40,
            height=30,
            byte_size=len(data),
            sort_order=n,
            is_active=True,
        )
        db.add(photo)
        photos.append(photo)
    db.flush()
    tag = create_tag(db, f"Natuur {MARK}")
    set_asset_tags(db, photos[0].id, [tag.id])
    db.commit()
    made = {"activity": activity.id, "photos": [p.id for p in photos], "tag": tag.id}
    db.close()
    return made


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    p = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 1000})
    login_met_sessie(p, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    yield p
    p.close()


def _query(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def _upload_href(page) -> str:
    return page.locator("#me-uploadknop a").get_attribute("href")


def _album(page, situation):
    page.goto("/admin/media")
    pagina_klaar(page)
    page.locator("#me-boom a", has_text=f"Herfstwandeling {MARK}").first.click()
    page.wait_for_url(re.compile(rf".*activity_id={situation['activity']}.*"))
    pagina_klaar(page)


def test_upload_carries_the_branch_and_lands_back_on_it(page, situation, tmp_path):
    _album(page, situation)
    # The filter state stands in the address: the tree is one GET of the page.
    assert _query(page.url)["activity_id"] == str(situation["activity"])
    href = _upload_href(page)
    assert _query(href)["kind"] == "activity_photo"
    assert _query(href)["activity_id"] == str(situation["activity"])

    # #1138: after a search (a fragment), the button still carries the branch.
    with htmx_afgerond(page):
        page.locator("#me-filter input[type=search]").fill("Bos")
    page.wait_for_function(
        "() => document.querySelectorAll('#me-lijst [data-row-link]').length === 1"
    )
    assert _query(page.url).get("q") == "Bos", "the search stands in the address"
    after = _query(_upload_href(page))
    assert after["activity_id"] == str(situation["activity"]) and after["q"] == "Bos"

    page.locator("#me-uploadknop a").click()
    page.wait_for_url("**/admin/media/nieuw?**")
    pagina_klaar(page)
    assert page.locator("#me-kind").input_value() == "activity_photo"
    assert page.locator("#me-activity").input_value() == str(situation["activity"])

    files = []
    for n in (1, 2):
        path = tmp_path / f"nieuw-{n}.png"
        path.write_bytes(_png((n * 60, 90, 40)))
        files.append(str(path))
    page.set_input_files("#me-files", files)
    assert "2 bestanden gekozen" in page.locator("[data-upload-chosen]").inner_text()
    page.get_by_role("button", name="Uploaden").click()
    page.wait_for_url(re.compile(r".*/admin/media\?.*"))
    pagina_klaar(page)
    back = _query(page.url)
    assert back["kind"] == "activity_photo" and back["activity_id"] == str(situation["activity"])
    assert page.locator("#me-lijst article[data-card]").count() == 4, (
        "two new pictures in the album"
    )


def test_a_tag_branch_starts_the_upload_on_that_tag(page, situation):
    page.goto(f"/admin/media?tag={situation['tag']}")
    pagina_klaar(page)
    assert _query(_upload_href(page))["tag"] == str(situation["tag"])
    page.locator("#me-uploadknop a").click()
    page.wait_for_url("**/admin/media/nieuw?**")
    pagina_klaar(page)
    ticked = page.locator(f'input[name="tag_ids"][value="{situation["tag"]}"]')
    assert ticked.is_checked(), "the upload starts with the tag chosen"


def test_the_arrows_stand_only_with_a_branch(page, situation):
    _album(page, situation)
    assert page.locator('#me-lijst [hx-post$="/verplaats"]').count() >= 2
    page.locator("#me-boom a", has_text="Alles").first.click()
    page.wait_for_url("**kind=alles**")
    pagina_klaar(page)
    assert page.locator("#me-lijst article[data-card]").count() >= 2
    assert page.locator('#me-lijst [hx-post$="/verplaats"]').count() == 0, "no arrows in Alles"


def test_a_refused_tag_change_shows_its_reason_above_the_cards(page, situation):
    page.goto(f"/admin/media?tag={situation['tag']}")
    pagina_klaar(page)
    page.fill("#me-tag-naam", "")
    with htmx_afgerond(page):
        page.locator("[data-media-tag]").get_by_role("button", name="Opslaan").click()
    banner = page.locator("#me-lijst [role=alert]").first
    banner.wait_for(state="visible")
    cards = page.locator("#me-lijst article[data-card]").first.bounding_box()
    assert banner.bounding_box()["y"] < cards["y"], "the reason stands above the cards"
    assert _query(page.url).get("tag") == str(situation["tag"]), "the tag stays chosen"


def test_the_record_remembers_the_list(page, situation):
    page.goto(
        f"/admin/media?kind=activity_photo&activity_id={situation['activity']}&year=2027&q=Beek"
    )
    pagina_klaar(page)
    page.locator("#me-lijst [data-row-link]", has_text=f"Beek {MARK}").click()
    page.wait_for_url(re.compile(rf".*/admin/media/{situation['photos'][1]}\?terug=.*"))
    pagina_klaar(page)

    page.get_by_role("link", name="Bewerken").click()
    page.wait_for_url("**bewerken=1**")
    pagina_klaar(page)
    page.fill("input[name=title]", f"Beek in de herfst {MARK}")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Opslaan").click()
    page.wait_for_url(re.compile(rf".*/admin/media/{situation['photos'][1]}\?terug=.*"))
    pagina_klaar(page)
    assert page.locator("h1").inner_text() == f"Beek in de herfst {MARK}"

    page.locator("[data-way-back]").click()
    page.wait_for_url(re.compile(r".*/admin/media\?.*"))
    pagina_klaar(page)
    state = _query(page.url)
    assert state == {
        "kind": "activity_photo",
        "activity_id": str(situation["activity"]),
        "year": "2027",
        "q": "Beek",
    }, state
    assert page.locator("#me-filter input[type=search]").input_value() == "Beek"
    assert page.locator("#me-lijst [data-row-link]", has_text="Beek in de herfst").count() == 1

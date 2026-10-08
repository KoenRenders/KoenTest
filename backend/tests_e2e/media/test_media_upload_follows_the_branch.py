"""E2E #1527: "+ Uploaden" starts from the branch chosen in the tree of
/admin/media, and the upload lands back on that branch with the new picture.

Three branches, as the issue names them: an activity of 2027 (Activiteiten ›
2027 › the activity), Logo's › Sponsorlogo, and a tag — and a fourth, Koen's
addition: Ontwerpbeelden › 2027 › the activity. Each walk is the board's:
click the branch in the tree, click "+ Uploaden", read the form, choose a file,
"Uploaden", and find the picture on the branch it came from.

Proven red against master `fcb88be1`: the library tree has no "Sponsorlogo"
branch, and after an upload from a tag the library returns to the activity
photos, not to the tag.
"""

from __future__ import annotations

import io
import os
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

MARK = secrets.token_hex(3)


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (30, 120, 60)).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def situation() -> dict:
    """An activity of 2027 with one photo (so the tree shows it), and a tag."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate
    from app.domains.auth.api import make_session_value
    from app.domains.media.api import MediaAsset, MediaKind, create_tag
    from tests.conftest import SEEDED_ADMIN_EMAIL

    db = SessionLocal()
    activity = Activity(name=f"Zomerkamp {MARK}", location="Miloheem")
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=date(2027, 7, 1)))
    data = _png()
    db.add(
        MediaAsset(
            kind=MediaKind.ACTIVITY_PHOTO,
            activity_id=activity.id,
            data=data,
            content_type="image/png",
            thumbnail=data,
            thumb_content_type="image/png",
            width=40,
            height=30,
            byte_size=len(data),
            title=f"Eerste foto {MARK}",
            sort_order=0,
            is_active=True,
        )
    )
    # Koen's addition: a design picture of the activity, so Ontwerpbeelden ›
    # 2027 › the activity is a branch.
    db.add(
        MediaAsset(
            kind=MediaKind.DESIGN_IMAGE,
            activity_id=activity.id,
            data=data,
            content_type="image/png",
            thumbnail=data,
            thumb_content_type="image/png",
            width=40,
            height=30,
            byte_size=len(data),
            title=f"Eerste ontwerp {MARK}",
            sort_order=0,
            is_active=True,
        )
    )
    tag = create_tag(db, f"Feest {MARK}")
    db.commit()
    out = {
        "activity": activity.id,
        "activity_name": activity.name,
        "tag": tag.id,
        "tag_name": tag.name,
        "session": make_session_value(SEEDED_ADMIN_EMAIL),
    }
    db.close()
    return out


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _upload(page, title: str, tmp_path) -> None:
    """From the upload form: a title, one file, "Uploaden"; wait for the library."""
    path = tmp_path / f"{title}.png"
    path.write_bytes(_png())
    page.fill("#me-title", title)
    page.set_input_files("#me-files", str(path))
    page.get_by_role("button", name="Uploaden").first.click()
    page.wait_for_url("**/admin/media?**")
    pagina_klaar(page)


def _on_a_card(page, title: str) -> int:
    """How many cards carry this title — a card shows it in its title field."""
    return page.locator(f'#me-lijst input[value="{title}"]').count()


def _tree_link(page, name: str):
    return page.locator("#me-boom a", has_text=name).first


def test_an_activity_branch_starts_and_ends_the_upload(browser, situation, tmp_path):
    page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 1000})
    login_met_sessie(page, situation["session"])
    page.goto("/admin/media?year=2027")
    pagina_klaar(page)
    _tree_link(page, situation["activity_name"]).click()
    pagina_klaar(page)

    page.get_by_role("link", name="+ Uploaden").click()
    pagina_klaar(page)
    assert page.input_value("#me-kind") == "activity_photo"
    assert page.input_value("#me-activity") == str(situation["activity"])

    _upload(page, f"Tweede foto {MARK}", tmp_path)
    assert f"activity_id={situation['activity']}" in page.url
    assert _on_a_card(page, f"Tweede foto {MARK}") >= 1, "the new picture is in view"
    page.close()


def test_the_sponsor_branch_starts_and_ends_the_upload(browser, situation, tmp_path):
    page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 1000})
    login_met_sessie(page, situation["session"])
    page.goto("/admin/media")
    pagina_klaar(page)
    _tree_link(page, "Sponsorlogo").click()
    pagina_klaar(page)

    page.get_by_role("link", name="+ Uploaden").click()
    pagina_klaar(page)
    assert page.input_value("#me-kind") == "sponsor"

    _upload(page, f"Bakker {MARK}", tmp_path)
    assert "kind=sponsor" in page.url
    assert _on_a_card(page, f"Bakker {MARK}") >= 1
    page.close()


def test_a_tag_branch_starts_and_ends_the_upload(browser, situation, tmp_path):
    page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 1000})
    login_met_sessie(page, situation["session"])
    page.goto("/admin/media")
    pagina_klaar(page)
    _tree_link(page, situation["tag_name"]).click()
    pagina_klaar(page)

    page.get_by_role("link", name="+ Uploaden").click()
    pagina_klaar(page)
    chosen = page.eval_on_selector_all(
        'input[name="tag_ids"]:checked', "els => els.map(e => e.value)"
    )
    assert chosen == [str(situation["tag"])], "the tag is the starting point"
    page.select_option("#me-kind", "page_image")

    _upload(page, f"Feestbeeld {MARK}", tmp_path)
    assert f"tag={situation['tag']}" in page.url, "back on the tag"
    assert _on_a_card(page, f"Feestbeeld {MARK}") >= 1
    page.close()


def test_a_design_branch_starts_and_ends_the_upload(browser, situation, tmp_path):
    """Koen's addition: Ontwerpbeelden › 2027 › the activity starts the upload as
    a design picture of that activity, and it lands back there."""
    page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 1000})
    login_met_sessie(page, situation["session"])
    page.goto("/admin/media?year=2027")
    pagina_klaar(page)
    branch = page.locator("#me-boom details", has_text="Ontwerpbeelden").first
    branch.locator("a", has_text=situation["activity_name"]).click()
    pagina_klaar(page)
    assert "kind=design_image" in page.url

    page.get_by_role("link", name="+ Uploaden").click()
    pagina_klaar(page)
    assert page.input_value("#me-kind") == "design_image"
    assert page.input_value("#me-activity") == str(situation["activity"])

    _upload(page, f"Tweede ontwerp {MARK}", tmp_path)
    assert "kind=design_image" in page.url and f"activity_id={situation['activity']}" in page.url
    assert _on_a_card(page, f"Tweede ontwerp {MARK}") >= 1
    page.close()

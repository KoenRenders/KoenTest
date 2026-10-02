"""E2E: the copied design's photo choice offers last year's photos (#1397).

Measured in the Design Studio editor of a copy, at 390 and 1280 px: the main
image choice holds an option group "Van <activity> (<year>)" with the source's
activity photo and design image, the chosen photo is selected, and the page is
no wider than the window.

Proven red against master `ee4fee11` (served from an export of it): the choice
held no option group and none of the source's pictures.
"""

import os
import secrets
import sys
from datetime import date

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1397"

# Since #1473 the slot is the picker: open it, and read its first group — the
# copy chain's photos — from the modal, and the hidden field that holds the choice.
_MEASURE = """() => {
  const box = document.querySelector('#mp-main_image_id');
  const sections = [...box.querySelectorAll('section')];
  const groups = sections.filter(s => s.querySelector('h4')).map(s => ({
    label: s.querySelector('h4').textContent.trim(),
    options: [...s.querySelectorAll('button[aria-label]')].map(
      b => Number((b.getAttribute('@click') || b.getAttribute('x-on:click') || '').match(/chosen = '(\\d+)'/)[1]))}));
  return {groups, selected: Number(document.querySelector('input[name="main_image_id"]').value),
          width: [document.documentElement.scrollWidth, innerWidth]};
}"""


def _copied_design() -> dict:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate, copy_activity
    from app.domains.designstudio.models import Design
    from app.domains.media.api import MediaAsset

    db = SessionLocal()
    try:
        name = f"Kerstherberg {secrets.token_hex(2)}"
        source = Activity(name=name)
        db.add(source)
        db.flush()
        db.add(ActivityDate(activity_id=source.id, start_date=date(2026, 12, 25)))
        assets = {}
        for kind, title in (("activity_photo", "Herberg vol"), ("design_image", "Kerstboom")):
            asset = MediaAsset(
                kind=kind,
                title=title,
                activity_id=source.id,
                data=b"png",
                content_type="image/png",
                byte_size=3,
                sort_order=0,
            )
            db.add(asset)
            db.flush()
            assets[kind] = asset.id
        db.add(
            Design(
                activity_id=source.id,
                duo_code="dark_green-golden_yellow",
                main_image_id=assets["activity_photo"],
            )
        )
        db.commit()
        copy = copy_activity(db, source.id, first_date=date(2027, 12, 25))
        design = db.query(Design).filter(Design.activity_id == copy.id).one()
        return {"design": design.id, "name": name, **assets}
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    data = _copied_design()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, data, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_the_photo_choice_offers_the_source_pictures(setup, width):
    b, data, session_value = setup
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        login_met_sessie(page, session_value)
        page.goto(f"/admin/ontwerpen/{data['design']}")
        pagina_klaar(page)
        slot = page.locator('input[name="main_image_id"]').locator("xpath=..")
        slot.get_by_role("button", name="Kies een afbeelding").click()
        page.locator("#mp-main_image_id h4").first.wait_for(state="visible", timeout=5000)
        m = page.evaluate(_MEASURE)
        print(f"MEASURE @{width}", m)
        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.locator("#mp-main_image_id").scroll_into_view_if_needed()
            page.screenshot(path=f"{SHOTS}/{width}-ontwerp-fotokeuze.png")

        # The order inside a group is `pick_options`' (sort order, newest first),
        # not this test's subject: which pictures, under which heading.
        assert [g["label"] for g in m["groups"]] == [f"Van {data['name']} (2026)"], m
        assert sorted(m["groups"][0]["options"]) == sorted(
            [data["activity_photo"], data["design_image"]]
        ), m
        assert m["selected"] == data["activity_photo"], "the chosen photo is selected"
        assert m["width"][0] <= m["width"][1], m
    finally:
        page.close()

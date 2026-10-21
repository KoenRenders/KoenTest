"""E2E: the audience *Eerdere deelnemers* in a browser (CR-36, #2026).

What only a browser proves: the list appears when the author picks the audience — before
the choice is saved, through the page's own fragment request — the ticks are part of the
record form and are stored by its one Opslaan (#2183), where the read page says who the
letter goes to; the choice survives a reload, and nothing sticks out at 390 px.
"""

import os
import sys

import pytest

import app.models  # noqa: F401  — the app first: the test process keeps the e2e database
from app.kernel.clock import belgian_today

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.meetings.test_nieuwsbrief_flow import (  # noqa: E402,F401
    _klikbaar,
    admin_page,
    browser,
)
from tests_e2e.newsletter_head import open_head_card, save_letter  # noqa: E402
from tests_e2e.schermen import htmx_afgerond  # noqa: E402

PHONE = 390


@pytest.fixture(scope="module", autouse=True)
def past_activities():
    from datetime import timedelta

    from app.database import SessionLocal
    from app.domains.activities.models import Activity, ActivityDate, Registration

    db = SessionLocal()
    made = []
    try:
        for name, days, addresses in (
            ("E2E Deelnemersquiz", 120, ("a@example.org", "b@example.org", "c@example.org")),
            ("E2E Deelnemers-BBQ", 60, ("b@example.org", "d@example.org")),
        ):
            activity = Activity(name=name, location="Dorpsplein")
            db.add(activity)
            db.flush()
            db.add(
                ActivityDate(
                    activity_id=activity.id, start_date=belgian_today() - timedelta(days=days)
                )
            )
            for address in addresses:
                db.add(
                    Registration(
                        activity_id=activity.id,
                        registration_type="INDIVIDUAL",
                        contact_name="Gast",
                        contact_email=address,
                        phone="0470000000",
                    )
                )
            made.append(activity.id)
        db.commit()
    finally:
        db.close()
    yield made
    db = SessionLocal()
    try:
        # Made for this run only: gone with their registrations, so no other test
        # finds a past activity it did not make.
        for model in (Registration, ActivityDate):
            db.query(model).filter(model.activity_id.in_(made)).delete(synchronize_session=False)
        db.query(Activity).filter(Activity.id.in_(made)).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_the_list_follows_the_audience_and_opslaan_stores_the_ticks(admin_page):  # noqa: F811
    page = admin_page
    page.set_viewport_size({"width": PHONE, "height": 1400})
    page.get_by_role("button", name="Nieuwe nieuwsbrief", exact=True).click()
    page.wait_for_selector("#nb-editor .ProseMirror", timeout=10_000)
    _klikbaar(page, "#nb-editor .ProseMirror")
    adres = page.url.split("?")[0]
    open_head_card(page)

    assert page.locator("#nb-deelnemers input[name=chosen]").count() == 0, "not before the audience"
    with htmx_afgerond(page):
        page.locator('input[name="audience"][value="participants"]').check()
    page.wait_for_selector("#nb-deelnemers input[name=chosen]", timeout=5_000)
    names = page.locator("#nb-deelnemers label").all_inner_texts()
    assert any("E2E Deelnemers-BBQ" in n for n in names) and any(
        "E2E Deelnemersquiz" in n for n in names
    )
    assert names.index(next(n for n in names if "BBQ" in n)) < names.index(
        next(n for n in names if "quiz" in n)
    ), "newest first"

    for name in ("E2E Deelnemersquiz", "E2E Deelnemers-BBQ"):
        page.locator("#nb-deelnemers label", has_text=name).locator("input").check()
    assert page.evaluate("document.documentElement.scrollWidth") <= PHONE

    # Subject, audience and ticks are stored by the one Opslaan: both stand after a reload,
    # and the read page says who the letter goes to.
    page.fill("#nb-onderwerp", "Aan de deelnemers")
    save_letter(page)
    page.goto(adres)
    sentence = page.locator("[data-participants-read] [data-audience-line]").first.inner_text()
    assert "4 adressen" in sentence, "four people on five registrations"
    open_head_card(page)
    page.wait_for_selector("#nb-deelnemers input[name=chosen]")
    assert page.locator("#nb-deelnemers input[name=chosen]:checked").count() == 2

    # Another audience takes the list away.
    with htmx_afgerond(page):
        page.locator('input[name="audience"][value="members"]').check()
    page.wait_for_function(
        "document.querySelectorAll('#nb-deelnemers input[name=chosen]').length === 0"
    )

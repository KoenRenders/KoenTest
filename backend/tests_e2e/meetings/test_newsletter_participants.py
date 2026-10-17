"""E2E: the audience *Eerdere deelnemers* in a browser (CR-36, #2026).

What only a browser proves: the list appears when the author picks the audience — before
the choice is saved, through the page's own fragment request — a tick puts the activity in
the letter and the sentence follows without a page load, the choice survives a reload, and
nothing sticks out at 390 px.
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


def test_the_list_follows_the_audience_and_a_tick_changes_the_sentence(admin_page):  # noqa: F811
    page = admin_page
    page.set_viewport_size({"width": PHONE, "height": 1400})
    page.get_by_role("button", name="+ Nieuwe nieuwsbrief").click()
    page.wait_for_selector("#nb-editor .ProseMirror", timeout=10_000)
    _klikbaar(page, "#nb-onderwerp")
    adres = page.url

    assert page.locator("#nb-deelnemers input[name=chosen]").count() == 0, "not before the audience"
    with htmx_afgerond(page):
        page.locator("input[name=audience][value=participants]").check()
    page.wait_for_selector("#nb-deelnemers input[name=chosen]", timeout=5_000)
    names = page.locator("#nb-deelnemers label").all_inner_texts()
    assert any("E2E Deelnemers-BBQ" in n for n in names) and any(
        "E2E Deelnemersquiz" in n for n in names
    )
    assert names.index(next(n for n in names if "BBQ" in n)) < names.index(
        next(n for n in names if "quiz" in n)
    ), "newest first"

    for name in ("E2E Deelnemersquiz", "E2E Deelnemers-BBQ"):
        box = page.locator("#nb-deelnemers label", has_text=name).locator("input")
        with htmx_afgerond(page):
            box.check()
    sentence = page.locator("#nb-deelnemers [data-audience-line]").first.inner_text()
    assert "4 adressen" in sentence, "four people on five registrations"
    assert page.evaluate("document.documentElement.scrollWidth") <= PHONE

    # The audience and the ticks stand after a reload.
    page.goto(adres)
    page.wait_for_selector("#nb-deelnemers input[name=chosen]")
    assert page.locator("#nb-deelnemers input[name=chosen]:checked").count() == 2
    assert "4 adressen" in page.locator("#nb-deelnemers [data-audience-line]").first.inner_text()

    # Another audience takes the list away.
    with htmx_afgerond(page):
        page.locator("input[name=audience][value=members]").check()
    page.wait_for_function(
        "document.querySelectorAll('#nb-deelnemers input[name=chosen]').length === 0"
    )

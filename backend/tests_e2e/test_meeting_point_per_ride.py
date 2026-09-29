"""E2E: a meeting has one point per ride, and the picker offers every ride (#1335).

A monthly ride with two rides since the previous meeting and three coming, the
last beyond the three-month horizon, plus a weekend with hours. At 390 px the new
meeting must show two evaluation points and three upcoming ones (two rides and the
weekend), each with the moment of its own date; the picker under "Volgende
activiteiten" must offer the ride beyond the horizon as a choice of its own, and
adding it must put a fourth upcoming point on the agenda. Nothing may stick out.

Proven red against master `08beaa85`, with a server built from an export of it:
"evaluation points: 1" — the whole monthly ride was one point, dated by its first
ride.
"""

import os
import secrets
import sys
from datetime import date, time

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_als_admin  # noqa: E402

PHONE = 390
MEETING_DAY = "2027-03-04"
SHOTS = "/scratch/shots_1335"

RIDES = [
    date(2027, 2, 6),
    date(2027, 2, 20),
    date(2027, 3, 6),
    date(2027, 4, 3),
    date(2027, 7, 3),  # beyond the horizon of 4 June 2027
]

# Per section heading: the label and meta of every point, and the right edge of
# the widest element in it, so a failure names what sticks out.
_POINTS = """(heading) => {
  const card = [...document.querySelectorAll('#vg-document h2')]
    .find(h => h.textContent.trim() === heading).closest('div.rounded-2xl');
  return [...card.querySelectorAll('[id^="vg-punt-"]')].map(p => {
    const spans = p.querySelectorAll('span');
    return {
      label: spans[0].textContent.trim(),
      meta: spans[1] ? spans[1].textContent.trim() : '',
      right: Math.max(...[...p.querySelectorAll('*')].map(e => e.getBoundingClientRect().right)),
    };
  });
}"""


def _add_activity(name: str, *rows: tuple) -> None:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate

    db = SessionLocal()
    try:
        activity = Activity(name=name, location="Miloheem")
        db.add(activity)
        db.flush()
        for start, end, start_time, end_time in rows:
            db.add(
                ActivityDate(
                    activity_id=activity.id,
                    start_date=start,
                    end_date=end,
                    start_time=start_time,
                    end_time=end_time,
                )
            )
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, email, make_session_value(email)
        b.close()


def _to_top(page, heading: str) -> None:
    """Scroll a section heading to the top, under the sticky header."""
    page.evaluate(
        """(text) => { const h = [...document.querySelectorAll('#vg-document h2')]
            .find(h => h.textContent.trim().startsWith(text));
          window.scrollTo(0, h.getBoundingClientRect().top + scrollY - 110); }""",
        heading,
    )


def _shot(page, name: str) -> None:
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        # The page arrives through a cross-fade; a shot during it shows two pages.
        page.wait_for_function(
            "() => document.getAnimations().every(a => a.playState !== 'running')"
        )
        page.screenshot(path=f"{SHOTS}/{name}.png")


def test_every_ride_is_its_own_point_and_its_own_choice(browser):
    tag = secrets.token_hex(2)
    ride = f"Fietsrit {tag}"
    weekend = f"Weekend {tag}"
    _add_activity(ride, *[(d, None, time(14, 0), time(17, 0)) for d in RIDES])
    _add_activity(weekend, (date(2027, 5, 14), date(2027, 5, 16), time(14, 0), time(17, 0)))

    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": PHONE, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto("/admin/vergaderingen/nieuw")
        page.fill("#vg-datum", MEETING_DAY)
        page.click("button[type=submit]")
        page.wait_for_selector("#vg-document", timeout=10_000)

        evaluation = [
            p
            for p in page.evaluate(_POINTS, "Evaluatie voorbije activiteiten")
            if p["label"] == ride
        ]
        upcoming = [
            p
            for p in page.evaluate(_POINTS, "Volgende activiteiten")
            if p["label"] in (ride, weekend)
        ]
        print("MEASURE evaluation", evaluation)
        print("MEASURE upcoming", upcoming)
        assert len(evaluation) == 2, f"evaluation points: {len(evaluation)}"
        assert [p["meta"].split(" · ")[0] for p in evaluation] == [
            "zaterdag 6 februari 2027 14u – 17u",
            "zaterdag 20 februari 2027 14u – 17u",
        ]
        assert [p["meta"].split(" · ")[0] for p in upcoming] == [
            "zaterdag 6 maart 2027 14u – 17u",
            "zaterdag 3 april 2027 14u – 17u",
            "vrijdag 14 mei 2027 14u – zondag 16 mei 2027 17u",
        ], "every ride within the horizon, and the weekend with begin and end"

        width = page.evaluate("document.documentElement.scrollWidth")
        widest = max(p["right"] for p in evaluation + upcoming)
        print("MEASURE width", width, "widest point", widest)
        assert width <= PHONE and widest <= PHONE, (width, widest)

        _to_top(page, "Evaluatie")
        _shot(page, "390-evaluatie")
        _to_top(page, "Volgende activiteiten")
        _shot(page, "390-volgende-activiteiten")

        card = page.locator(
            "#vg-document div.rounded-2xl", has=page.locator("h2", has_text="Volgende activiteiten")
        )
        card.get_by_role("button", name="Punt toevoegen").click()
        htmx_stil(page)
        page.fill("#vg-document input[name=q]", ride)
        options = page.locator("#vg-kiezer-resultaten form")
        # The search swaps the results after a 300 ms debounce: wait for the list
        # to have narrowed to this activity, not for the clock.
        expect(options).to_have_count(1)
        texts = options.all_inner_texts()
        print("MEASURE picker", texts)
        assert len(texts) == 1 and "zaterdag 3 juli 2027" in texts[0], texts
        button = options.first.locator("button[type=submit]").bounding_box()
        print("MEASURE picker button", button)
        assert button and button["x"] + button["width"] <= PHONE, button
        options.first.scroll_into_view_if_needed()
        _shot(page, "390-kiezer")

        options.first.locator("button[type=submit]").click()
        htmx_stil(page)
        after = [p for p in page.evaluate(_POINTS, "Volgende activiteiten") if p["label"] == ride]
        assert len(after) == 3, f"upcoming ride points after adding one: {len(after)}"
    finally:
        page.close()


def _make_it_an_old_meeting(meeting_id: int, activity_name: str) -> None:
    """Turn the meeting's points of this activity into one point from before #1335:
    no date, the activity as a whole, with a note — as the meeting of 3 September
    stands on PROD."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity
    from app.domains.meetings.api import SectionKind, sections_of
    from app.domains.meetings.models import Meeting, MeetingItem

    db = SessionLocal()
    try:
        activity = db.query(Activity).filter_by(name=activity_name).one()
        meeting = db.get(Meeting, meeting_id)
        evaluation = next(s for s in sections_of(db, meeting) if s.kind is SectionKind.EVALUATION)
        for item in db.query(MeetingItem).filter_by(meeting_id=meeting_id, activity_id=activity.id):
            db.delete(item)
        db.add(
            MeetingItem(
                meeting_id=meeting_id,
                section_id=evaluation.id,
                activity_id=activity.id,
                sort_key=min(d.start_date for d in activity.dates),
                notes="<p>Besproken vóór #1335</p>",
            )
        )
        db.commit()
    finally:
        db.close()


def test_an_existing_meeting_offers_every_ride_next_to_its_old_point(browser):
    """Koen's answer (a): an existing meeting does not change by itself; he adds the
    rides through the picker. So the picker must offer every ride separately, also
    next to an old point without a date, and adding one keeps the old point."""
    ride = f"Fietsrit {secrets.token_hex(2)}"
    _add_activity(
        ride,
        *[
            (d, None, time(14, 0), time(17, 0))
            for d in (date(2027, 7, 10), date(2027, 8, 7), date(2027, 8, 21))
        ],
    )

    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": PHONE, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto("/admin/vergaderingen/nieuw")
        page.fill("#vg-datum", "2027-09-02")
        page.click("button[type=submit]")
        page.wait_for_selector("#vg-document", timeout=10_000)
        meeting_id = int(page.url.rstrip("/").split("/")[-1])
        _make_it_an_old_meeting(meeting_id, ride)
        page.reload()
        page.wait_for_selector("#vg-document", timeout=10_000)

        old = [
            p
            for p in page.evaluate(_POINTS, "Evaluatie voorbije activiteiten")
            if p["label"] == ride
        ]
        print("MEASURE old point", old)
        assert [p["meta"].split(" · ")[0] for p in old] == ["10 juli 14u"], (
            "the old point looks as it did"
        )

        card = page.locator(
            "#vg-document div.rounded-2xl",
            has=page.locator("h2", has_text="Evaluatie voorbije activiteiten"),
        )
        card.get_by_role("button", name="Punt toevoegen").click()
        htmx_stil(page)
        page.fill("#vg-document input[name=q]", ride)
        options = page.locator("#vg-kiezer-resultaten form")
        expect(options).to_have_count(3)
        texts = options.all_inner_texts()
        print("MEASURE picker next to the old point", texts)
        assert [t.split("\n")[1] for t in texts] == [
            "zaterdag 21 augustus 2027 14u – 17u",
            "zaterdag 7 augustus 2027 14u – 17u",
            "zaterdag 10 juli 2027 14u – 17u",
        ], "every ride is its own choice, the most recent first"
        options.first.scroll_into_view_if_needed()
        _shot(page, "390-bestaande-vergadering-kiezer")

        options.first.locator("button[type=submit]").click()
        htmx_stil(page)
        after = [
            p
            for p in page.evaluate(_POINTS, "Evaluatie voorbije activiteiten")
            if p["label"] == ride
        ]
        print("MEASURE after adding", after)
        assert [p["meta"].split(" · ")[0] for p in after] == [
            "10 juli 14u",
            "zaterdag 21 augustus 2027 14u – 17u",
        ], "the old point stays and the ride joins it, in date order"
        _to_top(page, "Evaluatie")
        _shot(page, "390-bestaande-vergadering-na")
    finally:
        page.close()

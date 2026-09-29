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

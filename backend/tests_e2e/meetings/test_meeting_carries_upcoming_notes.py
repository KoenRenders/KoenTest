"""E2E: the note on an upcoming activity is in the next agenda's editor (#1355).

A previous meeting, sent, noted "Jan zorgt voor de tent" at a coming activity. The
new meeting, created through the screen at 390 px, shows that activity under
"Volgende activiteiten" with the note already in its editor, inside the card.

Proven red against `541d624a` (#1354), with a server built from an export of it:
the editor of the new point was empty.
"""

import os
import secrets
import sys
from datetime import date, datetime, time, timezone

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_als_admin  # noqa: E402

PHONE = 390
SHOTS = "/scratch/shots_1355"
NOTE = "Jan zorgt voor de tent"

_MEASURE = """(name) => {
  const card = [...document.querySelectorAll('#vg-document h2')]
    .find(h => h.textContent.trim() === 'Volgende activiteiten').closest('div.rounded-2xl');
  const point = [...card.querySelectorAll('[id^="vg-punt-"]')]
    .find(p => p.querySelector('span').textContent.trim() === name);
  const editor = point.querySelector('trix-editor');
  const r = editor.getBoundingClientRect();
  return {
    doc: document.documentElement.scrollWidth, vw: innerWidth,
    card_right: Math.round(card.getBoundingClientRect().right),
    editor_right: Math.round(r.right), editor_width: Math.round(r.width),
    editor_text: editor.textContent.trim(),
  };
}"""


def _previous_meeting_with_a_note(name: str) -> None:
    """A sent meeting on 3 February 2028 with a note at `name`, coming on 18 March."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityDate
    from app.domains.meetings.api import (
        MeetingStatus,
        SectionKind,
        create_meeting,
        document_of,
        update_item,
    )

    db = SessionLocal()
    try:
        activity = Activity(name=name, location="Miloheem")
        db.add(activity)
        db.flush()
        db.add(
            ActivityDate(
                activity_id=activity.id, start_date=date(2028, 3, 18), start_time=time(14, 0)
            )
        )
        db.commit()
        meeting = create_meeting(db, meeting_date=date(2028, 2, 3))
        upcoming = next(s for s in document_of(db, meeting) if s.kind is SectionKind.UPCOMING)
        point = next(i for i in upcoming.items if i.label == name)
        update_item(db, meeting, point.id, notes=f"<p>{NOTE}</p>")
        meeting.report_sent_at = datetime.now(timezone.utc)
        meeting.status = MeetingStatus.SENT
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


def test_the_next_agenda_has_the_note_in_its_editor(browser):
    name = f"Tentenkamp {secrets.token_hex(2)}"
    _previous_meeting_with_a_note(name)

    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": PHONE, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto("/admin/vergaderingen/nieuw")
        page.fill("#vg-datum", "2028-03-02")
        page.click("button[type=submit]")
        page.wait_for_selector("#vg-document", timeout=10_000)
        htmx_stil(page)

        m = page.evaluate(_MEASURE, name)
        print("MEASURE", m)
        assert m["editor_text"] == NOTE, f"the note did not come along: {m}"
        assert m["doc"] <= m["vw"] and m["editor_right"] <= m["card_right"], m
        assert m["editor_width"] > 200, m

        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.evaluate(
                """(text) => { const h = [...document.querySelectorAll('#vg-document h2')]
                    .find(h => h.textContent.trim() === text);
                  window.scrollTo(0, h.getBoundingClientRect().top + scrollY - 110); }""",
                "Volgende activiteiten",
            )
            page.wait_for_function(
                "() => document.getAnimations().every(a => a.playState !== 'running')"
            )
            page.screenshot(path=f"{SHOTS}/390-volgende-activiteiten.png")
    finally:
        page.close()

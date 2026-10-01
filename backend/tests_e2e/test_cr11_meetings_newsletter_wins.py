"""E2E: the CR-11 quick wins on meetings and the newsletter, measured at 390 px (#1391).

Each test measures its win in the rendered DOM, the measurement the issue asks
for, and saves a screenshot outside the repo:

- W4: one link to the circle page on `/admin/vergaderingen`, in the header, and
  it reads "Instellingen".
- W6: per meeting row, the status text occurs once.
- W7: no button with "Versturen"/"Verstuur" that ends neither in "…" nor names
  a count, on the four screens (meeting, meeting send step, newsletter editor,
  newsletter send step).
- W13: no report checkbox in Raakje's panel; one line says how many go along.

Proven red against master `eee37a9d` (served from an export of it): W4 found two
links, W6 found the status twice, W7 found "Verstuur agenda" and "Verstuur
verslag" on the meeting, and W13 found a checkbox. The newsletter's old last
button, "Versturen (2)", named a count and so passes this measurement too; its
new wording is proven in `tests/integration/test_cr11_meetings_newsletter_wins.py`.
"""

import os
import re
import secrets
import sys
from datetime import date, datetime, timedelta, timezone

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1391"
PHONE = {"width": 390, "height": 900}

_SEND_BUTTONS = """() => [...document.querySelectorAll('main a, main button')]
  .filter(e => e.offsetHeight && /verstu(ur|ren)/i.test(e.textContent))
  .map(e => e.textContent.replace(/\\s+/g, ' ').trim())"""


def _data() -> dict:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.meetings.api import MeetingStatus, create_meeting
    from app.domains.newsletter import service as nb
    from app.domains.newsletter.models import Audience, Subscriber, SubscriberStatus
    from tests.conftest import SEEDED_ADMIN_EMAIL

    tag = secrets.token_hex(3)
    db = SessionLocal()
    try:
        sent = create_meeting(db, meeting_date=date.today() - timedelta(days=3))
        sent.status = MeetingStatus.SENT
        sent.agenda_sent_at = datetime.now(timezone.utc) - timedelta(days=5)
        sent.report_sent_at = datetime.now(timezone.utc)
        upcoming = create_meeting(db, meeting_date=date.today() + timedelta(days=9))
        for n in range(2):
            db.add(
                Subscriber(
                    email=f"lezer-{tag}-{n}@example.org",
                    status=SubscriberStatus.CONFIRMED,
                    source="admin",
                    unsubscribe_token=f"e2e-{tag}-{n}",
                )
            )
        db.commit()
        letter = nb.create_newsletter(db, created_by=SEEDED_ADMIN_EMAIL)
        nb.update_draft(
            db,
            letter,
            subject=f"Najaar {tag}",
            body_html="<div>Tot binnenkort.</div>",
            audience=Audience.NON_MEMBERS,
        )
        return {"sent": sent.id, "upcoming": upcoming.id, "letter": letter.id}
    finally:
        db.close()


@pytest.fixture(scope="module")
def phone():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    data = _data()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = b.new_page(base_url=BASE, viewport=PHONE)
        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL))
        yield page, data
        b.close()


# Two of these screens are wider than a phone on master `eee37a9d` already,
# before any of these wins: the newsletter editor (408 px at 390, its form cards)
# and the meeting's send step (462 px, its check card). Reported separately, not
# measured here; every other screen must fit.
_WIDE_ON_MASTER = re.compile(r"^/admin/(nieuwsbrieven/\d+|vergaderingen/\d+/verstuur\?.*)$")


def _open(page, path: str, shot: str) -> None:
    page.goto(path)
    pagina_klaar(page)
    width = page.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
    print("MEASURE width", path, width)
    if not _WIDE_ON_MASTER.match(path):
        assert width[0] <= width[1], f"{path} is wider than the phone: {width}"
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/390-{shot}.png", full_page=True)


def test_w4_one_link_to_the_settings_in_the_header(phone):
    page, _ = phone
    _open(page, "/admin/vergaderingen", "w4-w6-vergaderingen")
    links = page.evaluate(
        """() => [...document.querySelectorAll('a[href="/admin/vergaderingen/kring"]')]
             .map(a => ({text: a.textContent.trim(),
                         inHeader: !!a.closest('[data-page-header]'),
                         visible: !!a.offsetHeight}))"""
    )
    print("MEASURE W4", links)
    assert len(links) == 1, links
    assert links[0]["text"] == "Instellingen" and links[0]["inHeader"] and links[0]["visible"]


def test_w6_the_status_once_per_row(phone):
    page, data = phone
    _open(page, "/admin/vergaderingen", "w4-w6-vergaderingen")
    row = page.locator(f'a[href="/admin/vergaderingen/{data["sent"]}"]').inner_text()
    print("MEASURE W6", repr(row))
    assert row.lower().count("verslag verstuurd") == 1, row
    assert "agenda verstuurd" not in row.lower()


@pytest.mark.parametrize(
    "path,shot",
    [
        ("/admin/vergaderingen/{upcoming}", "w7-vergadering"),
        ("/admin/vergaderingen/{upcoming}/verstuur?kind=agenda", "w7-vergadering-versturen"),
        ("/admin/nieuwsbrieven/{letter}", "w7-w13-nieuwsbrief"),
        ("/admin/nieuwsbrieven/{letter}/versturen", "w7-nieuwsbrief-versturen"),
    ],
)
def test_w7_a_send_button_leads_or_names_its_consequence(phone, path, shot):
    page, data = phone
    _open(page, path.format(**data), shot)
    buttons = page.evaluate(_SEND_BUTTONS)
    print("MEASURE W7", shot, buttons)
    assert buttons, f"no send button measured on {shot}"
    bad = [b for b in buttons if not b.endswith("…") and not re.search(r"\d", b)]
    assert not bad, f"a send button that neither leads nor counts: {bad}"


def test_w13_the_reports_are_a_line_not_a_choice(phone):
    page, data = phone
    _open(page, f"/admin/nieuwsbrieven/{data['letter']}", "w7-w13-nieuwsbrief")
    panel = page.locator("#nb-raakje")
    assert panel.count() == 1, "Raakje's panel is on the page"
    boxes = panel.locator('input[type="checkbox"][name="meeting_id"]').count()
    line = panel.get_by_text(re.compile(r"sinds de vorige nieuwsbrief")).first.inner_text()
    print("MEASURE W13", boxes, repr(line))
    assert boxes == 0

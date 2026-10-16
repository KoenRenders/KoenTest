"""E2E: one moment reads the same on four back-office screens (#1976).

For the same moment the newsletter showed 19:04 and the workbench, a form's
results and the e-mail log 17:04: the newsletter converted to Brussels on its
own, the others showed the stored UTC value. Since #1976 the display filter
converts (`app.i18n.local_moment`), so one moment made here — a subscriber, a
task, a form submission and a mail, all stamped with it — must read the same
clock time on the four screens, and that time is Brussels time.

The rows are made for this file and removed again.

Broken on purpose (15 October 2026, put back): `local_moment` returning the
moment unconverted → the four screens showed 20:34 for 22:34 and the assertion
named each of them.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

MARK = "E2E-1976"
ADDRESS = "een-klok-1976@example.com"


def _db():
    import app.main  # noqa: F401  the whole app, so the domain facades import in order
    from app.database import SessionLocal

    return SessionLocal()


def _moment() -> datetime:
    """A minute ago, on the minute: the newest row on every list, and a clock
    time that differs from UTC by one or two hours."""
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    return now.replace(second=0, microsecond=0)


@pytest.fixture(scope="module")
def world():
    import secrets

    from app.domains.auth.api import make_session_value
    from app.domains.forms.models import Form, FormSubmission
    from app.domains.mail.models import EmailLog
    from app.domains.newsletter.models import Subscriber, SubscriberSource
    from app.domains.workflow.api import create_task
    from app.domains.workflow.models import WorkflowTask
    from tests.conftest import SEEDED_ADMIN_EMAIL

    moment = _moment()
    db = _db()
    try:
        db.add(
            Subscriber(
                email=ADDRESS,
                source=SubscriberSource.ADMIN,
                unsubscribe_token=secrets.token_hex(16),
                created_at=moment,
            )
        )
        task = create_task(
            db,
            kind="kernel.job_gefaald",
            title=f"{MARK} één klok",
            subject_type="kernel_job",
            subject_id="0",
            required_role="ADMIN",
        )
        db.flush()
        task.created_at = moment
        form = Form(title=f"{MARK} formulier", share_token=secrets.token_hex(16))
        db.add(form)
        db.flush()
        db.add(FormSubmission(form_id=form.id, submitted_at=moment))
        db.add(EmailLog(recipient=ADDRESS, subject=f"{MARK} mail", created_at=moment))
        db.commit()
        ids = {"task": task.id, "form": form.id}
    finally:
        db.close()
    admin = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield {"browser": browser, "ids": ids, "moment": moment, "admin": make_session_value(admin)}
        browser.close()
    db = _db()
    try:
        db.query(EmailLog).filter(EmailLog.recipient == ADDRESS).delete(synchronize_session=False)
        db.query(Subscriber).filter(Subscriber.email == ADDRESS).delete(synchronize_session=False)
        db.query(WorkflowTask).filter(WorkflowTask.title.like(f"{MARK}%")).delete(
            synchronize_session=False
        )
        db.query(Form).filter(Form.title.like(f"{MARK}%")).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_one_moment_reads_the_same_brussels_time_on_four_screens(world):
    from app.kernel.clock import BELGIUM

    moment = world["moment"]
    brussels = moment.astimezone(BELGIUM).strftime("%d-%m-%Y %H:%M")
    utc = moment.strftime("%d-%m-%Y %H:%M")
    assert brussels != utc, "the moment must tell the two clocks apart"

    page = world["browser"].new_page(base_url=BASE, viewport={"width": 1280, "height": 900})
    login_met_sessie(page, world["admin"])
    shown = {}
    try:
        for screen, path, where in (
            (
                "newsletter",
                f"/admin/nieuwsbrieven/abonnees?q={ADDRESS}",
                f"tr:has-text('{ADDRESS}')",
            ),
            ("workbench", f"/admin/werkbank?q={MARK}", f'tr[data-task="{world["ids"]["task"]}"]'),
            ("form results", f"/admin/formulieren/{world['ids']['form']}/resultaten", "main"),
            ("e-mail log", f"/admin/e-maillog?q={ADDRESS}", f"tr:has-text('{MARK} mail')"),
        ):
            page.goto(path)
            pagina_klaar(page)
            shown[screen] = page.locator(where).first.inner_text()
    finally:
        page.close()

    wrong = {screen: text for screen, text in shown.items() if brussels not in text}
    assert not wrong, f"not {brussels} (Brussels) on: {wrong}"
    in_utc = [screen for screen, text in shown.items() if utc in text]
    assert not in_utc, f"{utc} (UTC) still shown on: {in_utc}"


#: The screens whose moment changed form or source, as a phone and a desktop see
#: them. Not the newsletter's subscribers: its table is 623 px wide at 390 px on
#: master already (measured 15 October 2026), with or without this change.
SCREENS = {
    "dashboard": "/admin",
    "newsletter-letters": "/admin/nieuwsbrieven",
    "workbench": f"/admin/werkbank?q={MARK}",
    "e-mail-log": f"/admin/e-maillog?q={ADDRESS}",
}


@pytest.mark.parametrize("width", [390, 1280])
def test_the_screens_with_a_moment_do_not_scroll_sideways(world, width):
    """The newsletter's moments changed form ("di 15 sep, 18:00" became
    "15-09-2026 18:00") and the dashboard's line its source: neither may push a
    screen wider than a phone. Set `E2E_PRINTS` to a folder to keep a print of
    each (outside the repository)."""
    page = world["browser"].new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    login_met_sessie(page, world["admin"])
    wider = {}
    try:
        for name, path in SCREENS.items():
            page.goto(path)
            pagina_klaar(page)
            scroll, inner = page.evaluate(
                "[document.documentElement.scrollWidth, window.innerWidth]"
            )
            if scroll > inner:
                wider[name] = scroll
            folder = os.environ.get("E2E_PRINTS")
            if folder:
                os.makedirs(folder, exist_ok=True)
                page.screenshot(path=os.path.join(folder, f"1976-{name}-{width}.png"))
    finally:
        page.close()
    assert not wider, f"wider than {width} px: {wider}"

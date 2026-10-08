"""E2E: a person can still send the public forms (#1297).

The guard against automated submissions drops what comes in faster than
`MIN_SECONDS` after the form was rendered — silently, with the ordinary thanks.
That silence is the trap: a limit set too strict would refuse real people, and
the screen would thank them all the same. So this test does not stop at the
thanks. It types at a person's pace and then looks in the database for the row
(and, for a message, the task for the board).

A quick person, not a slow one: 100 ms a key (a fast typist). With 60 ms a key
the public form went out 1.8 s after loading and a first limit of three seconds
dropped it — measured while building, and the reason the limit is two.

Proven red (29 September 2026): `MIN_SECONDS = 60` added to
`app/kernel/form_guard.py` → both tests fail on the missing row, while the
screens still said thanks. And with `MIN_SECONDS = 3` and 60 ms a key the public
form test failed the same way — the too-strict limit, caught.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

#: A quick typist's pace. Not a pause: every key is a real input event.
KEY_DELAY_MS = 100


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def visitor(browser):
    context = browser.new_context(base_url=BASE, viewport={"width": 390, "height": 844})
    yield context.new_page()
    context.close()


def _type(page, selector: str, text: str) -> None:
    page.locator(selector).press_sequentially(text, delay=KEY_DELAY_MS)


def _stored(model_name: str, **where) -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.forms.models import FormSubmission
    from app.domains.workflow.models import WorkflowTask

    model = {"submission": FormSubmission, "task": WorkflowTask}[model_name]
    db = SessionLocal()
    try:
        return db.query(model).filter_by(**where).count()
    finally:
        db.close()


def test_a_person_sends_a_message(visitor):
    name = f"Mens {secrets.token_hex(2)}"
    visitor.goto("/berichten")
    pagina_klaar(visitor)
    _type(visitor, "#b_naam", name)
    _type(visitor, "#b_email", "mens@example.com")
    _type(visitor, "#b_bericht", "Graag meer wandelingen in het najaar.")
    visitor.get_by_role("button", name="Verstuur bericht").click()
    visitor.wait_for_url("**/?bericht=verzonden", timeout=10_000)

    assert "goed ontvangen" in visitor.locator("main").inner_text()
    assert _stored("submission", submitter_name=name) == 1, (
        "the screen said thanks, but the message was dropped — the guard refused a person"
    )
    assert _stored("task", kind="bericht.behartigen") >= 1


def test_a_person_sends_a_public_form(visitor):
    name = f"Ploeg {secrets.token_hex(2)}"
    visitor.goto("/formulier/tok-e2e-open")
    pagina_klaar(visitor)
    _type(visitor, "#submitter_name", "Jo Mens")
    _type(visitor, "#submitter_email", "jo@example.com")
    visitor.get_by_label("Naam ploeg").press_sequentially(name, delay=KEY_DELAY_MS)
    visitor.get_by_role("button", name="Verzenden").click()
    # #1589: the thank-you page takes the form's place — no navigation to wait for.
    visitor.locator("[data-form-thanks]").wait_for(timeout=10_000)

    assert "Bedankt" in visitor.locator("main").inner_text()
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.forms.models import FormSubmissionAnswer

    db = SessionLocal()
    try:
        found = (
            db.query(FormSubmissionAnswer).filter(FormSubmissionAnswer.value_text == name).count()
        )
    finally:
        db.close()
    assert found == 1, "the screen said thanks, but the form was dropped"

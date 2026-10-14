"""E2E #1858 and #1859 — three more doors of the form builder say why they refuse,
where the button was pressed.

The route tests hold the answers (`forms/tests/test_deletes_say_why_1858.py`,
`forms/tests/test_builder_labels_say_why_1831.py`); this file holds what only a
browser can: that the sentence is **on the screen, by the button, in view** at
390 px, and — for a changed question — that what was typed is still there.

- deleting a form that holds the answers of a registration (#1858);
- deleting a submission that is those answers (#1858);
- a changed question that loses its label (#1859): it answers in its own form
  now, not in the builder's banner.

Set `E2E_PRINTS` to a folder to keep a print of each (outside the repository).

Proven red (locally, each put back): the decorator `says_why_in` taken off
`formulier_verwijderen` → the form's test fails on the banner that never comes;
`veld_bewerken` given back its banner answer → the question's test fails, the
form closes and its line stays empty.
"""

from __future__ import annotations

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402

FORM_RULE = "Dit formulier heeft antwoorden op inschrijvingen."
SUBMISSION_RULE = "Deze inzending zijn de antwoorden van een inschrijving."
QUESTION_RULE = "Elk veld heeft een vraag/label nodig."

_GEOMETRY = """(line) => {
  const banner = document.querySelector(line + ' [data-save-refusal]').getBoundingClientRect();
  return {
    in_view: banner.top >= 0 && banner.bottom <= window.innerHeight,
    sideways: document.documentElement.scrollWidth - window.innerWidth,
  };
}"""


@pytest.fixture(scope="module")
def form() -> dict:
    """A form with one question and one submission that is a registration's answers."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.forms.models import Form, FormField, FormSection, FormSubmission

    tag = secrets.token_hex(3)
    db = SessionLocal()
    try:
        made = Form(
            title=f"Inschrijving {tag}", slug=f"inschrijving-{tag}", status="draft", share_token=tag
        )
        db.add(made)
        db.flush()
        section = FormSection(form_id=made.id, title="Vooraf", position=0)
        db.add(section)
        db.flush()
        field = FormField(
            form_id=made.id, section_id=section.id, label="Welke maat?", field_type="text"
        )
        submission = FormSubmission(form_id=made.id, attached=True, submitter_name="Inschrijver")
        db.add_all([field, submission])
        db.commit()
        return {"id": made.id, "field": field.id, "submission": submission.id}
    finally:
        db.close()


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    session = make_session_value(os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL)
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        login_met_sessie(page, session)
        yield page
        browser.close()


def _refused(page, press, ends_with: str, *, confirm: bool = False):
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith(ends_with)
    ) as answered:
        press()
        if confirm:
            ok = page.locator("[data-dialog] [data-dialog-ok]")
            ok.wait_for(state="visible")
            ok.click()
    assert answered.value.status == 422
    htmx_stil(page)


def _measure(page, line: str, rule: str, name: str) -> None:
    banner = page.locator(f"{line} [data-save-refusal]")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text(rule)
    expect(page.locator("[data-save-refusal]")).to_have_count(1)
    measured = page.evaluate(_GEOMETRY, line)
    assert measured["in_view"], f"the banner is out of view: {measured}"
    assert measured["sideways"] <= 0, f"the page scrolls sideways: {measured}"
    folder = os.environ.get("E2E_PRINTS")
    if folder:
        # The confirmation dialog fades out after its OK; print once it is gone.
        page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running')")
        page.screenshot(path=os.path.join(folder, f"{name}-390.png"))
    print(f"\nMEASURED {name}: {measured}")


def test_deleting_a_form_that_holds_answers_says_why_by_its_button(page, form):
    page.goto(f"/admin/formulieren/{form['id']}")
    pagina_klaar(page)
    head = page.locator("#fb-formulier-melding").locator("xpath=../..")
    head.get_by_role("button", name="Bewerken").click()

    _refused(
        page,
        lambda: head.get_by_role("button", name="Verwijderen").click(),
        f"/admin/formulieren/{form['id']}/verwijderen",
        confirm=True,
    )

    _measure(page, "#fb-formulier-melding", FORM_RULE, "formulier-verwijderen")
    assert page.url.endswith(f"/admin/formulieren/{form['id']}"), page.url


def test_deleting_a_registrations_submission_says_why_in_its_row(page, form):
    page.goto(f"/admin/formulieren/{form['id']}/inzendingen")
    pagina_klaar(page)
    line = f"#fb-inzending-{form['submission']}-melding"
    row = page.locator(line).locator("xpath=..")

    _refused(
        page,
        lambda: row.get_by_role("button", name="Verwijderen").click(),
        f"/inzendingen/{form['submission']}/verwijderen",
        confirm=True,
    )

    _measure(page, line, SUBMISSION_RULE, "inzending-verwijderen")


def test_a_changed_question_says_why_in_its_own_form_and_keeps_what_was_typed(page, form):
    page.goto(f"/admin/formulieren/{form['id']}")
    pagina_klaar(page)
    card = page.locator(f"#fb-veld-{form['field']}").locator("xpath=..")
    card.get_by_role("button", name="Bewerken").click()
    question = page.locator(f"#fb-veld-{form['field']}")
    question.locator('[name="label"]').fill("   ")
    question.locator('[name="help_text"]').fill("Kies je gewone maat.")

    _refused(
        page,
        lambda: card.get_by_role("button", name="Opslaan").click(),
        f"/velden/{form['field']}",
    )

    _measure(page, f"#fb-veld-{form['field']}-melding", QUESTION_RULE, "vraag-wijzigen")
    # The form is still open, and what was typed is still there.
    expect(question.locator('[name="help_text"]')).to_be_visible()
    assert question.locator('[name="help_text"]').input_value() == "Kies je gewone maat."

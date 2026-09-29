"""E2E: deleting a chosen answer option is refused, with the reason in view (#1347).

A radio question with an option one submission chose. At 390 px the secretary
deletes that option through the builder and confirms. The builder must come back
with the reason in its error banner, inside the viewport, and the option must
still be there. Measured at 390 and 1280 px.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, htmx_stil, login_als_admin  # noqa: E402

SHOTS = "/scratch/shots_1347"
REASON = "1 inzending(en) kozen dit antwoord. Verwijderen zou hun antwoord wissen."

_MEASURE = """(reason) => {
  const banner = [...document.querySelectorAll('[role=alert], .rounded-lg, div')]
    .filter(el => el.textContent.trim().includes(reason))
    .sort((a, b) => a.textContent.length - b.textContent.length)[0];
  const r = banner ? banner.getBoundingClientRect() : null;
  return {
    doc: document.documentElement.scrollWidth, vw: innerWidth,
    banner: r && {left: Math.round(r.left), right: Math.round(r.right),
                  top: Math.round(r.top), bottom: Math.round(r.bottom),
                  visible: r.width > 0 && r.height > 0},
  };
}"""


def _form_with_a_chosen_option() -> tuple[int, int]:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.forms.models import (
        Form,
        FormField,
        FormFieldOption,
        FormSubmission,
        FormSubmissionAnswer,
    )

    tag = secrets.token_hex(3)
    db = SessionLocal()
    try:
        form = Form(title=f"Dagkeuze {tag}", slug=f"dagkeuze-{tag}", status="open", share_token=tag)
        db.add(form)
        db.flush()
        field = FormField(form_id=form.id, label="Welke dag?", field_type="radio", position=0)
        db.add(field)
        db.flush()
        saturday = FormFieldOption(field_id=field.id, label="Zaterdag", position=0)
        db.add(saturday)
        db.flush()
        submission = FormSubmission(form_id=form.id)
        db.add(submission)
        db.flush()
        db.add(
            FormSubmissionAnswer(
                submission_id=submission.id, field_id=field.id, value_option_id=saturday.id
            )
        )
        db.commit()
        return form.id, saturday.id
    finally:
        db.close()


def _option_exists(option_id: int) -> bool:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.forms.models import FormFieldOption

    db = SessionLocal()
    try:
        return db.get(FormFieldOption, option_id) is not None
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


@pytest.mark.parametrize("width", [390, 1280])
def test_deleting_a_chosen_option_is_refused_in_view(browser, width):
    form_id, option_id = _form_with_a_chosen_option()
    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto(f"/admin/formulieren/{form_id}")
        htmx_stil(page)

        delete = page.locator(f'[hx-post$="/opties/{option_id}/verwijderen"]').first
        delete.scroll_into_view_if_needed()
        delete.click()
        with htmx_afgerond(page):
            page.get_by_role("button", name="Bevestigen").click()
        htmx_stil(page)

        m = page.evaluate(_MEASURE, REASON)
        print(f"MEASURE @{width}", m)
        assert m["banner"] and m["banner"]["visible"], f"@{width}: no reason on the screen"
        assert m["doc"] <= m["vw"] and m["banner"]["right"] <= m["vw"], m
        assert _option_exists(option_id), "the chosen option is still there"

        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.get_by_text(REASON).first.scroll_into_view_if_needed()
            page.wait_for_function(
                "() => document.getAnimations().every(a => a.playState !== 'running')"
            )
            page.screenshot(path=f"{SHOTS}/{width}-weigering.png")
    finally:
        page.close()

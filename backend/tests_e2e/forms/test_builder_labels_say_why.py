"""E2E #1831 — the form builder says why it refuses a label, in the form that was saved.

The route tests (`forms/tests/test_builder_labels_say_why_1831.py`) hold the
answer; this file holds what only a browser can: that the sentence is **on the
screen, in that form, in view**, at 390 px — and that what was typed in the
form, and in another form of the builder, is still there.

What the browser lets through by itself: a label of spaces (`required` is
satisfied by a space). No attribute is taken off here.

Three forms: a new question, a new option, a changed option.

Set `E2E_PRINTS` to a folder to keep a print of each (outside the repository).

Proven red (locally, restored): the decorator `says_why_in` taken off
`optie_toevoegen` → the new option's test fails on the banner that never comes.
"""

from __future__ import annotations

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402

QUESTION_RULE = "Elk veld heeft een vraag/label nodig."
OPTION_RULE = "Elke optie heeft een label nodig."

_GEOMETRY = """([line, box]) => {
  const banner = document.querySelector(line + ' [data-save-refusal]').getBoundingClientRect();
  const frame = document.querySelector(line).closest(box).getBoundingClientRect();
  return {
    inside: banner.left >= frame.left - 0.5 && banner.right <= frame.right + 0.5
            && banner.top >= frame.top - 0.5 && banner.bottom <= frame.bottom + 0.5,
    in_view: banner.top >= 0 && banner.bottom <= window.innerHeight,
    sideways: document.documentElement.scrollWidth - window.innerWidth,
  };
}"""


@pytest.fixture(scope="module")
def form() -> dict:
    """A form with one section, a choice question with one option."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.forms.models import Form, FormField, FormFieldOption, FormSection

    tag = secrets.token_hex(3)
    db = SessionLocal()
    try:
        made = Form(
            title=f"Wandeling {tag}", slug=f"wandeling-{tag}", status="draft", share_token=tag
        )
        db.add(made)
        db.flush()
        section = FormSection(form_id=made.id, title="Vooraf", position=0)
        db.add(section)
        db.flush()
        field = FormField(
            form_id=made.id,
            section_id=section.id,
            label="Welke afstand?",
            field_type="radio",
            position=0,
        )
        db.add(field)
        db.flush()
        option = FormFieldOption(field_id=field.id, label="5 km", position=0)
        db.add(option)
        db.commit()
        return {"id": made.id, "section": section.id, "field": field.id, "option": option.id}
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


def _open(page, form) -> None:
    page.goto(f"/admin/formulieren/{form['id']}")
    pagina_klaar(page)


def _refused(page, press, ends_with: str):
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith(ends_with)
    ) as answered:
        press()
    assert answered.value.status == 422
    htmx_stil(page)


def _measure(page, line: str, box: str, rule: str, name: str) -> None:
    banner = page.locator(f"{line} [data-save-refusal]")
    expect(banner).to_be_visible()
    expect(banner).to_contain_text("Opslaan is niet gelukt.")
    expect(banner).to_contain_text(rule)
    expect(page.locator("[data-save-refusal]")).to_have_count(1)
    measured = page.evaluate(_GEOMETRY, [line, box])
    assert measured["inside"], f"the banner stands outside its form: {measured}"
    assert measured["in_view"], f"the banner is out of view: {measured}"
    assert measured["sideways"] <= 0, f"the page scrolls sideways: {measured}"
    folder = os.environ.get("E2E_PRINTS")
    if folder:
        page.screenshot(path=os.path.join(folder, f"{name}-390.png"))
    print(f"\nMEASURED {name}: {measured}")


def test_a_new_question_of_spaces_says_why_in_its_form(page, form):
    _open(page, form)
    page.get_by_role("button", name="+ Vraag in deze sectie").click()
    new = page.locator(f'form[hx-post$="/admin/formulieren/{form["id"]}/velden"]').first
    new.locator('[name="label"]').fill("   ")
    new.locator('[name="help_text"]').fill("Kies wat je aankan.")

    _refused(page, lambda: new.get_by_role("button", name="Opslaan").click(), "/velden")

    _measure(
        page, f"#fb-veld-nieuw-{form['section']}-melding", "form", QUESTION_RULE, "vraag-nieuw"
    )
    # What was typed is still there: the answer is the banner alone.
    assert new.locator('[name="help_text"]').input_value() == "Kies wat je aankan."


def test_a_new_option_of_spaces_says_why_in_its_row(page, form):
    _open(page, form)
    page.get_by_role("button", name="+ Optie toevoegen").click()
    row = page.locator(f'form[hx-post$="/velden/{form["field"]}/opties"]')
    row.locator('[name="label"]').fill("   ")
    row.locator('[name="is_other"]').check()

    _refused(page, lambda: row.get_by_role("button", name="Opslaan").click(), "/opties")

    _measure(page, f"#fb-optie-nieuw-{form['field']}-melding", "form", OPTION_RULE, "optie-nieuw")
    assert row.locator('[name="is_other"]').is_checked()


def test_an_option_that_loses_its_label_says_why_and_leaves_the_others(page, form):
    _open(page, form)
    # Something unsaved in ANOTHER form of the builder: the new-option row.
    page.get_by_role("button", name="+ Optie toevoegen").click()
    other = page.locator(f'form[hx-post$="/velden/{form["field"]}/opties"]')
    other.locator('[name="label"]').fill("10 km")
    row = page.locator(f'form[hx-post$="/opties/{form["option"]}"]')
    row.locator('[name="label"]').fill("   ")

    _refused(
        page, lambda: row.get_by_role("button", name="Opslaan").click(), f"/opties/{form['option']}"
    )

    _measure(page, f"#fb-optie-{form['option']}-melding", "form", OPTION_RULE, "optie-wijzigen")
    assert other.locator('[name="label"]').input_value() == "10 km"
    assert page.locator(f"#fb-optie-nieuw-{form['field']}-melding").inner_text().strip() == ""

    # A good save after the refusal: the builder is drawn again, every line empty.
    row.locator('[name="label"]').fill("7 km")
    with page.expect_response(lambda r: r.request.method == "POST" and r.status == 200):
        row.get_by_role("button", name="Opslaan").click()
    htmx_stil(page)
    expect(page.locator("[data-save-refusal]")).to_have_count(0)
    expect(page.locator(f'form[hx-post$="/opties/{form["option"]}"] [name="label"]')).to_have_value(
        "7 km"
    )

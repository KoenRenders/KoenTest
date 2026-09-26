"""E2E: the "Anders" text of a choice question (#683), in a browser.

Written as part of the characterisation of CR-12 phase 4, before the form
builder's `field_type` comparisons leave the templates: the server-side
snapshots (`tests/test_form_field_types_characterisation.py`) see the markup,
not what Alpine does with it. Two behaviours are browser-only:

- typing in the "Anders" box ticks the "Anders" option;
- choosing another option (radio) or unticking "Anders" (checkbox) empties
  the box, because the server ticks "Anders" again as soon as text arrives.

The wizard and the jumps between sections have their own browser tests in
`test_formulier_wizard_stap.py`.

Broken on purpose to check that these tests can go red: the group's
`@change` handler removed from the radio branch of `_formulier_veld.html` →
the radio clearing test falls over; the `@input` on the text box removed →
both typing tests fall over, and the checkbox unticking test with them (the
box never got ticked, so there was nothing to untick). Measured on 26
September 2026 against a local server.
"""
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def anders_formulier():
    """One radio and one checkbox question, each with an "Anders" option."""
    import secrets

    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.forms.models import Form, FormField, FormFieldOption

    db = SessionLocal()
    token = "e2e-anders-" + secrets.token_urlsafe(6)
    form = Form(title="E2E Anders", status="open", is_anonymous=True, share_token=token)
    db.add(form)
    db.flush()
    ids = {}
    for position, kind in enumerate(("radio", "checkbox")):
        field = FormField(form_id=form.id, field_type=kind, label=f"Vraag {kind}",
                          position=position)
        db.add(field)
        db.flush()
        db.add(FormFieldOption(field_id=field.id, label="Gewoon", position=0))
        db.add(FormFieldOption(field_id=field.id, label="Anders", position=1,
                               is_other=True))
        ids[kind] = field.id
    db.commit()
    db.close()
    return token, ids


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE)
        yield p
        browser.close()


def _open(page, token):
    page.goto(f"/formulier/{token}")
    pagina_klaar(page)


def _option(page, field_id, label):
    return page.locator(f'[data-veld="f{field_id}"] label', has_text=label).locator(
        "input").first


@pytest.mark.parametrize("kind", ["radio", "checkbox"])
def test_typing_in_anders_ticks_the_option(page, anders_formulier, kind):
    token, ids = anders_formulier
    _open(page, token)
    anders = _option(page, ids[kind], "Anders")
    expect(anders).not_to_be_checked()

    page.fill(f"#f{ids[kind]}_other", "iets eigens")

    expect(anders).to_be_checked()


def test_choosing_another_radio_empties_the_anders_box(page, anders_formulier):
    token, ids = anders_formulier
    _open(page, token)
    page.fill(f"#f{ids['radio']}_other", "iets eigens")

    _option(page, ids["radio"], "Gewoon").check()

    expect(page.locator(f"#f{ids['radio']}_other")).to_have_value("")


def test_unticking_the_anders_checkbox_empties_its_box(page, anders_formulier):
    token, ids = anders_formulier
    _open(page, token)
    page.fill(f"#f{ids['checkbox']}_other", "iets eigens")

    _option(page, ids["checkbox"], "Anders").uncheck()

    expect(page.locator(f"#f{ids['checkbox']}_other")).to_have_value("")

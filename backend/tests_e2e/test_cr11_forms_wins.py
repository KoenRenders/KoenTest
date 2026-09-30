"""E2E: the CR-11 quick wins in the form builder, measured at 390 px (#1391).

- W14: on the builder no action with the word "Export"; on the Inzendingen tab
  exactly one ("Export (.ods)").
- W18: the opened import block holds one input, of type `file`.

Each test saves a screenshot outside the repo. Proven red against master
`112ed593` (served from an export of it): W14 found "Export" on the builder.
W18 fails there before its measurement, since the button was still called
"JSON-import"; its paste box is proven by the assertion in
`app/domains/forms/tests/test_cr11_builder_actions.py`.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHOTS = "/scratch/shots_1391"
PHONE = {"width": 390, "height": 900}

_EXPORTS = """() => [...document.querySelectorAll('main a, main button')]
  .filter(e => e.offsetHeight && /export/i.test(e.textContent))
  .map(e => e.textContent.replace(/\\s+/g, ' ').trim())"""


def _form() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.forms.models import Form, FormField

    tag = secrets.token_hex(3)
    db = SessionLocal()
    try:
        form = Form(
            title=f"Opruimdag {tag}", slug=f"opruimdag-{tag}", status="open", share_token=tag
        )
        db.add(form)
        db.flush()
        db.add(FormField(form_id=form.id, label="Je naam", field_type="text", position=0))
        db.commit()
        return form.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def phone():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    form_id = _form()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = b.new_page(base_url=BASE, viewport=PHONE)
        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL))
        yield page, form_id
        b.close()


def _shot(page, name: str) -> None:
    width = page.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
    print("MEASURE width", name, width)
    assert width[0] <= width[1], f"{name} is wider than the phone: {width}"
    if os.path.isdir("/scratch"):
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/390-{name}.png", full_page=True)


def test_w14_export_sits_on_the_submissions_tab(phone):
    page, form_id = phone
    page.goto(f"/admin/formulieren/{form_id}")
    pagina_klaar(page)
    builder = page.evaluate(_EXPORTS)
    _shot(page, "w14-bouwer")
    page.goto(f"/admin/formulieren/{form_id}/inzendingen")
    pagina_klaar(page)
    tab = page.evaluate(_EXPORTS)
    _shot(page, "w14-inzendingen")
    print("MEASURE W14", builder, tab)
    assert not [a for a in builder if a.startswith("Export")], builder
    assert tab == ["Export (.ods)"], tab


def test_w18_the_import_block_holds_one_file_input(phone):
    page, form_id = phone
    page.goto(f"/admin/formulieren/{form_id}")
    pagina_klaar(page)
    page.get_by_role("button", name="Definitie importeren (JSON)…").click()
    block = page.locator('form[hx-post$="/json-import"]')
    block.wait_for(state="visible")
    inputs = block.evaluate(
        """f => [...f.querySelectorAll('input, textarea, select')]
             .filter(e => e.type !== 'hidden').map(e => e.tagName.toLowerCase() + ':' + e.type)"""
    )
    block.scroll_into_view_if_needed()
    _shot(page, "w18-import")
    print("MEASURE W18", inputs)
    assert inputs == ["input:file"], inputs

"""E2E: the help text of a question grows with its content in the builder (#1379).

A question whose help text has three lines. At 390 and 1280 px, opening the
question shows the whole help text without a scrollbar, and typing a fourth line
makes the field grow. On master the help text was a single input line.

Proven red against master `4cc36c76` (the test on the unchanged code): an `input`,
not a `textarea`. The first build of this issue was red too, twice, and both times
in the kit's autogrow: a box that started hidden kept its `rows` (56 px for 76 px
of text) until the first keystroke, and a grown box stayed 2 px short of its text
because the border was not counted.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_als_admin  # noqa: E402

SHOTS = "/scratch/shots_1379"
HELP = "Kom op tijd.\nBreng je eigen beker mee.\nParkeren kan achter de zaal."

_MEASURE = """(id) => {
  const el = document.getElementById(id);
  return {tag: el.tagName.toLowerCase(), client: el.clientHeight, scroll: el.scrollHeight,
          height: Math.round(el.getBoundingClientRect().height),
          doc: document.documentElement.scrollWidth, vw: innerWidth};
}"""


def _form_with_help() -> tuple[int, int]:
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
        field = FormField(
            form_id=form.id, label="Je naam", field_type="text", position=0, help_text=HELP
        )
        db.add(field)
        db.commit()
        return form.id, field.id
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
def test_the_help_text_shows_whole_and_grows(browser, width):
    form_id, field_id = _form_with_help()
    b, email, session_value = browser
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        login_als_admin(page, email, session_value)
        page.goto(f"/admin/formulieren/{form_id}")
        htmx_stil(page)
        card = page.locator("div.border.rounded-lg", has=page.locator(f"#fh-{field_id}")).first
        card.get_by_role("button", name="Bewerken").first.click()
        field = page.locator(f"#fh-{field_id}")
        field.scroll_into_view_if_needed()

        opened = page.evaluate(_MEASURE, f"fh-{field_id}")
        print(f"MEASURE @{width} opened", opened)
        assert opened["tag"] == "textarea", opened
        assert opened["scroll"] <= opened["client"] + 1, (
            f"@{width}: a scrollbar on opening: {opened}"
        )

        field.press("End")
        field.press("Control+End")
        field.type("\nVragen? Bel de voorzitter.")
        grown = page.evaluate(_MEASURE, f"fh-{field_id}")
        print(f"MEASURE @{width} grown", grown)
        assert grown["height"] > opened["height"], f"@{width}: it did not grow: {grown}"
        assert grown["scroll"] <= grown["client"] + 1, grown
        assert grown["doc"] <= grown["vw"], grown

        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.wait_for_function(
                "() => document.getAnimations().every(a => a.playState !== 'running')"
            )
            page.screenshot(path=f"{SHOTS}/{width}-hulptekst.png")
    finally:
        page.close()

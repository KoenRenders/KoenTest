"""E2E: a refused enterprise or VAT number shows its reason on its field, in view
(#1545).

The refusal of #1517 worked — 422, the input kept, nothing stored — but its
banner stands at the top of a long form, and Opslaan at its bottom: measured
before the fix, the viewport stayed at the Nummers section and the banner was
out of view, so the save read as "nothing happened". Now the reason also
stands below the field (`<id>-fout`, linked by `aria-describedby`), and this
measures that it is in the viewport after the click, at 1440 and 390 px.

Two screens share the form: an account's organisation in the platform
workspace, and "Onze organisatie" in a tenant workspace. Each gets an
enterprise number with a wrong check number and a Belgian VAT number with one;
neither is stored.

Red against master `c7785fe4`: there is no `#org-enterprise_number-fout`.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, PLATFORM, login_met_sessie, pagina_klaar  # noqa: E402

# Invented numbers whose check fails: 97 − 01234567 % 97 = 49, not 89.
CASES = (
    ("enterprise_number", "0123.456.789"),
    ("vat_number", "BE 0123.456.789"),
)

_IN_VIEW = """id => {
  const e = document.getElementById(id);
  if (!e || !e.checkVisibility()) return null;
  const r = e.getBoundingClientRect();
  return {top: r.top, bottom: r.bottom, height: innerHeight, text: e.innerText};
}"""


@pytest.fixture(scope="module", params=[(1440, 900), (390, 844)], ids=["1440", "390"])
def browser_context(request):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    width, height = request.param
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        ctx = b.new_context(viewport={"width": width, "height": height})
        p = ctx.new_page()
        login_met_sessie(p, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
        # #1535: platform administration answers in the platform workspace only.
        login_met_sessie(p, make_session_value(SEEDED_ADMIN_EMAIL), PLATFORM)
        yield p
        b.close()


def _account_screen(page) -> str:
    page.goto(PLATFORM + "/admin/organisaties")
    pagina_klaar(page)
    href = page.locator("a[href^='/admin/organisaties/']:not([href$='/nieuw'])").first
    return PLATFORM + href.get_attribute("href")


@pytest.mark.parametrize("screen", ["account", "own"])
@pytest.mark.parametrize("field, text", CASES, ids=[c[0] for c in CASES])
def test_the_reason_stands_on_the_field_in_view(browser_context, screen, field, text):
    page = browser_context
    url = _account_screen(page) if screen == "account" else BASE + "/admin/organisatie"
    page.goto(url)
    pagina_klaar(page)
    control = page.locator(f"#org-{field}")
    before = control.input_value()

    control.fill(text)
    with page.expect_response(lambda r: r.request.method == "POST") as answer:
        page.locator("#org-form button[type=submit]").first.click()
    pagina_klaar(page)

    assert answer.value.status == 422
    error = page.evaluate(_IN_VIEW, f"org-{field}-fout")
    print("MEASURE", screen, field, error)
    assert error, "no reason below the field"
    assert "controlegetal klopt niet" in error["text"]
    assert 0 <= error["top"] and error["bottom"] <= error["height"], (
        f"the reason is out of view: {error}"
    )
    assert page.locator(f"#org-{field}").input_value() == text, "what was typed is gone"
    assert page.locator(f"#org-{field}").get_attribute("aria-describedby") == f"org-{field}-fout"

    page.goto(url)
    pagina_klaar(page)
    assert page.locator(f"#org-{field}").input_value() == before, "the refused number was saved"

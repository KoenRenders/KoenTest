"""E2E: a refused save shows its reason, keeps the page whole, and saves
nothing (#1515).

Measured in a browser, because the defect lived between the server and htmx:
a refusal answers 422 with the form and a banner, and htmx 2.0.4 does not swap
a 4xx answer — on master the user saw only the generic toast "Er ging iets
mis; je wijziging is niet bewaard" and never what to correct. Since #1515 the
shells swap an HTML 422 (`ui.htmx_ux`), so every such form shows its banner
through that one place; a JSON 422 keeps the error path.

Three screens with that pattern, each with a refusal the service really makes:
- the organisation: a street without a house number;
- the tenant editor: a module switched off that another module needs;
- a new member: no person at all (the browser's own checks off, as a script
  sending the form directly could).

For each: the answer stays 422, the page's own banner (`#main [role=alert]`)
names the reason, no generic toast, one shell (a full page swapped into its
form would nest the shell — measured on the new-member form before its target
was set), and nothing is saved where that can be read back.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

_STATE = """() => ({
  banners: [...document.querySelectorAll('#main [role=alert]')].map(e => e.innerText),
  toasts: [...document.querySelectorAll('#toasts [role=alert]')].map(e => e.innerText),
  shells: document.querySelectorAll('#admin-zijbalk').length,
})"""


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        login_met_sessie(p, make_session_value(SEEDED_ADMIN_EMAIL))
        yield p
        b.close()


def _submit(page, button, url_part: str):
    with page.expect_response(lambda r: r.request.method == "POST" and url_part in r.url) as answer:
        button.click()
    pagina_klaar(page)
    return answer.value.status, page.evaluate(_STATE)


def _first_link(page, prefix: str) -> str:
    page.goto(prefix)
    pagina_klaar(page)
    return page.locator(f"a[href^='{prefix}/']:not([href$='/nieuw'])").first.get_attribute("href")


def _assert_shown(status, state, reason: str):
    print("MEASURE", status, state)
    assert status == 422, "a refusal keeps its status"
    assert state["banners"] and reason in state["banners"][0], (
        f"the reason is not on the page: {state}"
    )
    assert not state["toasts"], f"only the generic toast: {state}"
    assert state["shells"] == 1, f"the page swapped into the form, the shell nested: {state}"


def test_the_organisation_shows_why(page):
    adres = _first_link(page, "/admin/organisaties")
    page.goto(adres)
    pagina_klaar(page)
    voor = page.locator("#street").input_value()

    page.locator("#street").fill("Weigerstraat")
    page.locator("#house_number").fill("")
    status, state = _submit(page, page.locator("#org-form button[type=submit]").first, adres)

    _assert_shown(status, state, "Huisnummer")
    assert page.locator("#street").input_value() == "Weigerstraat", "what was typed is gone"
    page.goto(adres)
    pagina_klaar(page)
    assert page.locator("#street").input_value() == voor, "the refused address was saved"


def test_the_tenant_editor_shows_why(page):
    # A unit, not the list's first row: that is the platform, which has
    # Activiteiten off since #1523.
    page.goto("/admin/tenants")
    pagina_klaar(page)
    adres = (
        page.locator("a[href^='/admin/tenants/']:not([href$='/nieuw'])")
        .filter(has_text="Raak Millegem")
        .first.get_attribute("href")
    )
    page.goto(adres)
    pagina_klaar(page)
    activities = page.locator("#tn-form input[type=checkbox][value=activities]").first
    assert activities.is_checked(), "the seeded tenant has activities on, else this proves nothing"

    activities.uncheck()
    status, state = _submit(page, page.locator("button[type=submit][form=tn-form]").first, adres)

    _assert_shown(status, state, "Activiteiten")
    page.goto(adres)
    pagina_klaar(page)
    assert page.locator("#tn-form input[type=checkbox][value=activities]").first.is_checked(), (
        "the refused module set was saved"
    )


def test_a_new_member_without_a_person_shows_why(page):
    page.goto("/admin/leden/nieuw")
    pagina_klaar(page)
    page.evaluate(
        "() => { const f = document.querySelector('form[hx-post=\"/admin/leden\"]');"
        " f.noValidate = true; f.querySelectorAll('[required]').forEach(e => e.removeAttribute('required')); }"
    )

    status, state = _submit(
        page, page.locator("form[hx-post='/admin/leden'] button[type=submit]").first, "/admin/leden"
    )

    _assert_shown(status, state, "hoofdlid")

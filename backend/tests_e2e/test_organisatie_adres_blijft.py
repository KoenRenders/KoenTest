"""E2E: the address of an organisation survives a save and a reload (#1244).

The bug was invisible from inside one session: the save flushed the address
without committing it, and the screen that came back — rendered from that same
session — showed the new address. Only a reload, a new request on a new session,
showed it gone. So this test does exactly that, in a browser on a phone-sized
screen (390 px, the norm for this site): type the address, press Opslaan,
reload, read the fields.

It also measures what a person needs to do this on a phone: the Opslaan button
lies inside the screen width, and the page does not scroll sideways.

Broken on purpose to check that this test can go red: the `db.commit()` at the
end of `save_organization` removed → after the reload the street is empty.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

ORGANISATION_ID = 1  # the legal entity: an editor, no site of its own
WIDTH = 390


@pytest.fixture(scope="module")
def operator():
    """A back-office user with the OPERATOR role, and its session value."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole

    email = f"e2e-1244-{secrets.token_hex(3)}@example.org"
    db = SessionLocal()
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
    db.commit()
    db.close()
    return make_session_value(email)


@pytest.fixture(scope="module")
def page(operator):
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE, viewport={"width": WIDTH, "height": 844})
        login_met_sessie(p, operator)
        yield p
        browser.close()


def test_the_address_is_still_there_after_a_reload(page):
    page.goto(f"/admin/organisaties/{ORGANISATION_ID}")
    pagina_klaar(page)
    straat = f"E2E-straat {secrets.token_hex(2)}"
    page.fill("#street", straat)
    page.fill("#house_number", "12")
    postcode = page.locator("#postal_code option:not([value=''])").first.get_attribute("value")
    page.select_option("#postal_code", postcode)

    opslaan = page.get_by_role("button", name="Opslaan")
    box = opslaan.bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= WIDTH, (
        f"Opslaan lies outside the {WIDTH}px screen: {box}"
    )
    assert page.evaluate("document.documentElement.scrollWidth") <= WIDTH, (
        "the page scrolls sideways on a phone"
    )

    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/admin/organisaties/{ORGANISATION_ID}" in r.url
    ) as resp:
        opslaan.click()
    assert resp.value.status == 200

    page.reload()
    pagina_klaar(page)
    expect(page.locator("#street")).to_have_value(straat)
    expect(page.locator("#house_number")).to_have_value("12")
    expect(page.locator("#postal_code")).to_have_value(postcode)

    # Put it back: an empty street and number remove the address.
    page.fill("#street", "")
    page.fill("#house_number", "")
    with page.expect_response(lambda r: r.request.method == "POST"):
        page.get_by_role("button", name="Opslaan").click()
    page.reload()
    pagina_klaar(page)
    expect(page.locator("#street")).to_have_value("")

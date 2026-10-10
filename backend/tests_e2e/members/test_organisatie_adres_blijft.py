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

from tests_e2e.schermen import PLATFORM, login_met_sessie, pagina_klaar  # noqa: E402

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
        # #1535: platform administration answers in the platform workspace only.
        p = browser.new_page(base_url=PLATFORM, viewport={"width": WIDTH, "height": 844})
        login_met_sessie(p, operator, PLATFORM)
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


def test_the_email_field_refuses_what_is_no_address_and_says_so_at_the_field(page):
    """#1853: the organisation's e-mail field took any text. What a browser lets
    through by itself — `naam@domein` without a dot — is refused by the rule of
    the contact detail, at the field, and what was typed comes back.

    Set `E2E_PRINTS` to a folder to keep a print (outside the repository)."""
    typed = "secretariaat@zonderpunt"
    page.goto(f"/admin/organisaties/{ORGANISATION_ID}")
    pagina_klaar(page)
    page.locator('input[name="email"]').fill(typed)

    with page.expect_response(
        lambda r: r.request.method == "POST" and f"/admin/organisaties/{ORGANISATION_ID}" in r.url
    ) as resp:
        page.get_by_role("button", name="Opslaan").click()
    assert resp.value.status == 422
    pagina_klaar(page)
    page.wait_for_function("() => document.getAnimations().every(a => a.playState !== 'running')")

    field = page.locator('input[name="email"]')
    expect(field).to_have_value(typed)
    expect(field).to_have_attribute("aria-invalid", "true")
    described = field.get_attribute("aria-describedby")
    reason = page.locator(f"#{described.split()[-1]}")
    expect(reason).to_contain_text("Vul een geldig e-mailadres in.")
    field.scroll_into_view_if_needed()
    below = reason.bounding_box()["y"] - (
        field.bounding_box()["y"] + field.bounding_box()["height"]
    )
    assert 0 <= below <= 24, f"the reason does not stand right below its field: {below} px"
    assert page.evaluate("document.documentElement.scrollWidth") <= WIDTH, (
        "the page scrolls sideways on a phone"
    )
    folder = os.environ.get("E2E_PRINTS")
    if folder:
        page.screenshot(path=os.path.join(folder, "emailveld-organisatie-390.png"))
    print(f"\nMEASURED organisation: the reason stands {below} px below its field")

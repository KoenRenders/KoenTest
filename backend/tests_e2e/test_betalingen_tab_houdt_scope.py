"""E2E: confirming a payment on an activity's Betalingen tab keeps the list in
that activity (#1247), on a phone-sized screen (390 px).

Koen's path on UAT: open an activity, go to its Betalingen tab, confirm a
payment. The list that came back held every payment of the association. This
test walks that path in a browser — the Bevestig link, the confirmation modal,
the swapped list — and **counts the records** before and after: "a list came
back" is true for both outcomes. The records of a second activity must never
appear.

Broken on purpose to check that this test can go red: the `hx-headers` taken off
`#betalingen-lijst` in `_betalingen_scherm.html` → after the confirmation the
other activity's payment is in the list.
"""
import os
import re
import secrets
import sys

import httpx
import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402

WIDTH = 390


@pytest.fixture(scope="module")
def two_activities():
    """Two paid activities, one registration each, and a FINANCE user."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole
    from tests.conftest import seed_activity_with_product

    db = SessionLocal()
    ids = []
    for _ in range(2):
        activity, component, product = seed_activity_with_product(db, price="10.00", is_free=False)
        ids.append((activity.id, component.id, product.id))
    email = f"e2e-1247-{secrets.token_hex(3)}@example.org"
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="FINANCE"))
    db.commit()
    db.close()

    names = []
    for activity_id, component_id, product_id in ids:
        name = f"E2E {secrets.token_hex(3)}"
        names.append(name)
        httpx.post(f"{BASE}/activiteiten/{activity_id}/inschrijven/{component_id}",
                   data={"contact_name": name, "contact_email": "e2e-1247@example.org",
                         "phone": "047", f"product_{product_id}": "1",
                         "payment_method": "transfer"}, timeout=30)
    return {"activity": ids[0][0], "mine": names[0], "other": names[1],
            "session": make_session_value(email)}


@pytest.fixture(scope="module")
def page(two_activities):
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE, viewport={"width": WIDTH, "height": 844})
        login_met_sessie(p, two_activities["session"])
        yield p
        browser.close()


def _records(page) -> set[str]:
    return set(re.findall(r"open === '([^']+)'",
                          page.inner_html("#betalingen-lijst")))


def test_confirming_on_the_activity_tab_keeps_the_activity(page, two_activities):
    page.goto(f"/admin/activiteiten/{two_activities['activity']}/betalingen")
    pagina_klaar(page)
    lijst = page.locator("#betalingen-lijst")
    before = _records(page)
    assert before, "the tab shows no payment — is the setup still right?"
    assert two_activities["mine"] in lijst.inner_text()
    assert two_activities["other"] not in lijst.inner_text()

    lijst.get_by_text("Bevestig", exact=True).first.click()
    with page.expect_response(lambda r: r.request.method == "POST"
                              and r.url.endswith("/bevestigen")) as resp:
        page.get_by_role("button", name="Bevestigen").click()
    assert resp.value.status == 200
    htmx_stil(page)

    after = _records(page)
    assert after == before, (
        f"{len(before)} record(s) before the confirmation, {len(after)} after")
    assert two_activities["other"] not in lijst.inner_text(), (
        "the other activity's payment came back: the scope was lost")

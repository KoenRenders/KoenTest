"""E2E: mark a delivery as bounced and send it again (#2188).

A sent letter, the row's ⋯ at 390 px: it holds *Teruggekomen*, the menu is
reachable (not cut off by the table's scroll box), the click gives the row the
badge *Teruggekomen*, the button names the number, and *Toch aangekomen* takes it
back. When `E2E_PRINT_DIR` is set the prints are taken there (never in the repo).
"""

import os
import sys
from datetime import datetime, timezone

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests._letter import letter_doc
from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

ROWS = (("an@example.com", "sent"), ("bob@example.com", "sent"), ("cleo@example.com", "failed"))


@pytest.fixture(scope="module")
def letter():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.newsletter.models import (
        Audience,
        Delivery,
        DeliveryKind,
        DeliveryStatus,
        LetterStatus,
        Newsletter,
    )

    db = SessionLocal()
    try:
        sent = Newsletter(
            subject="E2E Teruggekomen",
            body_document=letter_doc("<div>Beste</div>"),
            audience=Audience.BOTH,
            status=LetterStatus.SENT,
            sent_body_html="<div>Beste</div>",
        )
        db.add(sent)
        db.flush()
        moment = datetime(2026, 10, 8, 18, 51, tzinfo=timezone.utc)
        for address, status in ROWS:
            db.add(
                Delivery(
                    newsletter_id=sent.id,
                    email=address,
                    kind=DeliveryKind.MEMBER,
                    status=DeliveryStatus(status),
                    sent_at=moment,
                    error="adres geweigerd door de mailserver" if status == "failed" else None,
                )
            )
        db.commit()
        letter_id = sent.id
    finally:
        db.close()

    yield letter_id

    db = SessionLocal()
    try:
        db.query(Delivery).filter(Delivery.newsletter_id == letter_id).delete(
            synchronize_session=False
        )
        db.query(Newsletter).filter(Newsletter.id == letter_id).execution_options(
            include_deleted=True
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _print(page, name):
    folder = os.environ.get("E2E_PRINT_DIR")
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    height = page.evaluate("document.documentElement.scrollHeight")
    page.set_viewport_size({"width": 390, "height": height})
    page.screenshot(
        path=os.path.join(folder, name), clip={"x": 0, "y": 0, "width": 390, "height": height}
    )
    page.set_viewport_size({"width": 390, "height": 900})


def test_the_row_menu_marks_a_delivery_and_takes_it_back(browser, letter):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 900})
    try:
        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
        page.goto(f"/admin/nieuwsbrieven/{letter}")
        pagina_klaar(page)
        button = page.locator("[data-resend-failed] button")
        assert button.inner_text().strip() == "Opnieuw versturen naar 1 mislukt adres"

        row = page.locator("[data-deliveries] tbody tr", has_text="an@example.com")
        row.locator("[data-row-menu-trigger]").click()
        item = row.locator("[data-row-menu] button", has_text="Teruggekomen")
        item.wait_for(state="visible")
        box = item.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390, box
        assert page.evaluate("document.documentElement.scrollWidth") == 390
        _print(page, "rij-menu-390.png")

        item.click()
        page.wait_for_url(f"**/admin/nieuwsbrieven/{letter}")
        pagina_klaar(page)
        row = page.locator("[data-deliveries] tbody tr", has_text="an@example.com")
        assert "Teruggekomen" in row.locator("[data-cell=status]").inner_text()
        button = page.locator("[data-resend-failed] button")
        assert button.inner_text().strip() == "Opnieuw versturen naar 2 mislukte adressen"
        _print(page, "knop-en-rij-390.png")

        row.locator("[data-row-menu-trigger]").click()
        row.locator("[data-row-menu] button", has_text="Toch aangekomen").click()
        page.wait_for_function(
            "() => document.querySelector('[data-resend-failed] button')"
            ".innerText.includes('1 mislukt adres')"
        )
        assert (
            "Verstuurd"
            in page.locator("[data-deliveries] tbody tr", has_text="an@example.com")
            .locator("[data-cell=status]")
            .inner_text()
        )
    finally:
        page.close()

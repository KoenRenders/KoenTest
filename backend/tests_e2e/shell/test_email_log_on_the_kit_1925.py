"""E2E: the e-mail log on the kit's list, and a mail's own page (#1925).

Koen, 16 October 2026: "geef een email maar een read-only eigen scherm". Walked
at 390 and 1 440 px: the list does not scroll sideways and a row's subject opens
the mail's page; that page names the subject, the recipient and the status, the
mail stands in its sandboxed frame as wide as the column, and Verwijderen under
Acties asks its question and leads back to the list, without the mail. `MEASURE`
lines print what was measured; set `E2E_PRINTS` to keep a print of each width.

Made-up mails on the example domain, removed again afterwards.

Broken on purpose (16 October 2026, put back): the row link's `href` pointed at
the list again → "the subject opens the mail's page" is red.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

LIST = "/admin/e-maillog"


@pytest.fixture(scope="module")
def mails():
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mail.models import EmailLog

    tag = secrets.token_hex(3)
    db = SessionLocal()
    made = []
    try:
        for name, status, error in (
            ("verstuurd", "sent", None),
            ("mislukt", "failed", "De server weigerde het adres."),
        ):
            log = EmailLog(
                recipient=f"{name}-{tag}@example.com",
                subject=f"Proefmail {name} {tag}",
                email_type="other",
                status=status,
                error_message=error,
                body=f"<p>Beste {name}</p><ul><li>Een punt</li></ul>",
            )
            db.add(log)
            db.flush()
            made.append(log.id)
        db.commit()
        yield tag, made
    finally:
        db.rollback()
        db.query(EmailLog).filter(EmailLog.id.in_(made)).delete(synchronize_session=False)
        db.commit()
        db.close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        yield b
        b.close()


def _open(browser, width, path):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    page.goto(path)
    pagina_klaar(page)
    return page


def _print(page, name):
    folder = os.environ.get("E2E_PRINTS")
    if folder:
        os.makedirs(folder, exist_ok=True)
        page.screenshot(path=os.path.join(folder, name), full_page=False)


@pytest.mark.parametrize("width", [390, 1440])
def test_the_list_and_a_mails_page(browser, mails, width):
    tag, ids = mails
    page = _open(browser, width, f"{LIST}?q={tag}")
    try:
        rows = page.locator("[data-mail]")
        assert rows.count() == 2, "the search finds the two mails"
        scroll = page.evaluate("document.documentElement.scrollWidth")
        print(f"MEASURE list {width}: page {scroll}")
        assert scroll == width, "the list scrolls sideways"
        _print(page, f"1925-emaillog-lijst-{width}.png")

        failed = page.locator(f'[data-mail="{ids[1]}"]')
        expect(failed).to_contain_text("De server weigerde het adres.")
        failed.locator("[data-row-link], a").first.click()
        page.wait_for_url(f"**{LIST}/{ids[1]}**")
        pagina_klaar(page)
        # The boosted navigation crossfades the two pages: measure and print the
        # page once the transition has ended, not a frame of both.
        page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running')")

        expect(page.locator("h1")).to_have_text(f"Proefmail mislukt {tag}")
        expect(page.locator("[data-facts]")).to_contain_text(f"Aan: mislukt-{tag}@example.com")
        expect(page.locator("[data-mail-error]")).to_contain_text("De server weigerde het adres.")
        frame = page.locator("[data-mail-body]").bounding_box()
        column = page.locator("[data-form-column]").bounding_box()
        scroll = page.evaluate("document.documentElement.scrollWidth")
        print(
            f"MEASURE page {width}: frame {frame['width']:.0f} of column {column['width']:.0f}, page {scroll}"
        )
        assert scroll == width, "the mail's page scrolls sideways"
        assert frame["width"] >= column["width"] - 40, "the mail is as wide as its column"
        # As tall as the mail, not a fixed box (the master CLI's eye on the print):
        # the frame's height is the mail's own.
        # The mail's own bottom (its body's box and margin), not the frame's
        # scrollHeight, which is never less than the frame itself.
        inner = page.evaluate(
            """() => { const b = document.querySelector('[data-mail-body]').contentDocument.body;
                       return Math.round(b.getBoundingClientRect().bottom
                              + parseFloat(getComputedStyle(b).marginBottom)); }"""
        )
        frame = page.locator("[data-mail-body]").bounding_box()
        print(f"MEASURE page {width}: frame height {frame['height']:.0f}, mail {inner}")
        # The frame also holds the last block's bottom margin (a list's 8 px, measured).
        assert inner <= frame["height"] <= inner + 16, "the frame is not as tall as the mail"
        assert frame["height"] < 150, "a two-line mail in a tall frame"
        _print(page, f"1925-emaillog-mail-{width}.png")
    finally:
        page.close()


def test_a_mail_is_deleted_from_its_page(browser, mails):
    tag, ids = mails
    page = _open(browser, 1440, f"{LIST}/{ids[0]}?terug={LIST}%3Fq%3D{tag}")
    try:
        page.get_by_role("button", name="Acties").click()
        page.locator("[data-actions-menu] [role=menuitem]", has_text="Verwijderen").click()
        page.get_by_role("button", name="Bevestigen").click()
        page.wait_for_url(f"**{LIST}?q={tag}")
        pagina_klaar(page)
        expect(page.locator(f'[data-mail="{ids[0]}"]')).to_have_count(0)
        expect(page.locator(f'[data-mail="{ids[1]}"]')).to_have_count(1)
    finally:
        page.close()

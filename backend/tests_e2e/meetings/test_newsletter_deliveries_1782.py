"""E2E: the Per adres table of a sent newsletter (#1782).

Koen, 8 October 2026, at about 770 px: "Wanneer" broke over two lines in every
row and "Reden" was squeezed by the address column.

The address is what this list is scanned by, so the repair may not be paid by
it (the master CLI's read of the first build, where an ordinary address of 21
characters broke in the middle). Measured here at 390 and at 770 px, with
addresses of 14, 21, 24, 33 and 60 characters and three rows with a reason:

- an address of up to some 32 characters stands on one line; only the one that
  is longer than the cap breaks, inside the cap, with its whole value;
- the moment stands on one line in every row;
- the reason has a width of its own and runs over a few lines at most;
- the page does not scroll sideways; at 770 px the table fits its card, at
  390 px it scrolls inside the card (the kit's rule for a list).

Measured while building, at 390 px: without `min-w-0` on the card's grid item
the page itself was 633 px wide — the item followed its widest content.

A sent letter with six deliveries on the example domain is made for this file
and removed again.
"""

import os
import sys
from datetime import datetime, timezone

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

LONG = "een.heel.lang.adres.van.een.lid.met.dubbele.naam@example.com"
ROWS = (
    ("an@example.com", "sent", None),
    ("geweigerd@example.com", "failed", "adres geweigerd door de mailserver"),
    ("voornaam.achternaam21@example.com", "failed", "mailserver niet bereikbaar (tijdelijk)"),
    (LONG, "sent", None),
    ("overgeslagen@example.com", "skipped", None),
    ("druk@example.com", "failed", "tijdelijk geweigerd door de mailserver"),
)
TABLE = """() => {
  const table = document.querySelector('[data-deliveries]'), wrap = table.parentElement;
  const lines = el => { const r = document.createRange(); r.selectNodeContents(el);
    return new Set([...r.getClientRects()].map(x => Math.round(x.top))).size; };
  const rows = [...table.querySelectorAll('tbody tr')].map(tr => {
    const cell = name => tr.querySelector(`[data-cell=${name}]`);
    const span = cell('address').querySelector('[data-address]');
    return { address: span.innerText.trim(),
      address_lines: Math.round(span.offsetHeight / parseFloat(getComputedStyle(span).lineHeight)),
      when: lines(cell('when')), reason: cell('reason').innerText.trim(),
      reason_lines: lines(cell('reason')),
      reason_width: Math.round(cell('reason').getBoundingClientRect().width) };
  });
  return { rows, table: Math.round(table.getBoundingClientRect().width), room: wrap.clientWidth,
    page: [window.innerWidth, document.documentElement.scrollWidth] };
}"""


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
            subject="E2E Per adres",
            body_html="<div>Beste</div>",
            audience=Audience.BOTH,
            status=LetterStatus.SENT,
        )
        db.add(sent)
        db.flush()
        moment = datetime(2026, 10, 8, 18, 51, tzinfo=timezone.utc)
        for address, status, error in ROWS:
            db.add(
                Delivery(
                    newsletter_id=sent.id,
                    email=address,
                    kind=DeliveryKind.MEMBER,
                    status=DeliveryStatus(status),
                    sent_at=moment,
                    error=error,
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


@pytest.mark.parametrize("width", [390, 770])
def test_an_address_keeps_its_line_the_moment_too_and_the_reason_has_room(browser, letter, width):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
        page.goto(f"/admin/nieuwsbrieven/{letter}")
        pagina_klaar(page)
        m = page.evaluate(TABLE)
        print("MEASURE per adres", width, m)

        by_address = {row["address"]: row for row in m["rows"]}
        assert set(by_address) == {address for address, _s, _e in ROWS}, "an address is cut off"
        for address, row in by_address.items():
            wanted = 2 if address == LONG else 1
            assert row["address_lines"] == wanted, (address, row)
        assert [row["when"] for row in m["rows"]] == [1] * len(ROWS), "the moment breaks"
        with_reason = [row for row in m["rows"] if row["reason"]]
        assert len(with_reason) == 3
        for row in with_reason:
            assert row["reason_width"] >= 112 and row["reason_lines"] <= 3, row
        # The page never scrolls sideways; the table may, inside its card.
        assert m["page"] == [width, width], m["page"]
        assert m["room"] <= width
        if width == 770:
            assert m["table"] <= m["room"], "at 770 px the four columns fit the card"
    finally:
        page.close()

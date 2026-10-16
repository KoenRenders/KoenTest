"""E2E: the AI call log on the kit's table (#1925; Koen, 16 October 2026, "a").

Eight values in the kit's seven places: the model and its provider share one
optional column that stands on a wide screen only, the duration keeps the other.
The page takes the kit lists' width (`max-w-none`): in the shell's reading column
of 1 024 px the table never reached the 1 100 px the model's column needs.
Measured at 390, 1 150, 1 280 and 1 440 px with six made-up calls: no sideways
scroll, the cost inside the frame, a row of 57 px on a wide screen (the model may
take two lines in it), the
duration from 1 150 px, Model · Provider from 1 280 px, a card per call on a
phone. Before
(measured 16 October 2026 at 1 280 px) the table was 1 134 px in a frame of
1 022 px: the cost stood outside it, and a row was 77 px with the model on
three lines. `MEASURE` lines print what was measured; set `E2E_PRINTS` to keep a
print of each width.

Broken on purpose (16 October 2026, put back): the old hand-built table, given the
new view (`engine` in the model's cell, no provider column) on the new page width
→ red at 390 px (the model's column stands on a phone: no cards) and at 1 150 px
(a row of more than one line). At 1 280 and 1 440 px the old table fits too, once
the page is as wide as the kit's lists.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

PAGE = "/admin/info/ai-kosten"

CALLS = [
    (
        "admin",
        "reporting",
        "bestuur@example.com",
        "mistral-medium-latest",
        "mistral",
        "ok",
        2400,
        "0.003120",
        "EUR",
    ),
    ("public", "chat", "", "mistral-small-latest", "mistral", "ok", 900, "0.000410", "EUR"),
    (
        "admin",
        "image",
        "secretaris@example.com",
        "flux-pro-1.1",
        "bfl",
        "ok",
        14200,
        "0.045000",
        "USD",
    ),
    (
        "admin",
        "newsletter_drafting",
        "voorzitter.met.lange.naam@example.com",
        "mistral-large-latest",
        "mistral",
        "error",
        30000,
        None,
        None,
    ),
    ("public", "chat", "", "mistral-small-latest", "mistral", "blocked", None, None, None),
    (
        "admin",
        "dictation",
        "bestuur@example.com",
        "voxtral-mini-latest",
        "mistral",
        "ok",
        5100,
        "0.002000",
        "EUR",
    ),
]


@pytest.fixture(scope="module")
def calls():
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.chatbot.models import AiCallLog

    db = SessionLocal()
    made = []
    try:
        now = datetime.now(timezone.utc)
        for i, (surface, cap, actor, model, provider, status, ms, amount, cur) in enumerate(CALLS):
            log = AiCallLog(
                surface=surface,
                capability=cap,
                actor=actor,
                model=model,
                provider=provider,
                status=status,
                duration_ms=ms,
                cost_amount=Decimal(amount) if amount else None,
                cost_currency=cur,
                created_at=now - timedelta(minutes=i),
            )
            db.add(log)
            db.flush()
            made.append(log.id)
        db.commit()
        yield made
    finally:
        db.rollback()
        db.query(AiCallLog).filter(AiCallLog.id.in_(made)).delete(synchronize_session=False)
        db.commit()
        db.close()


_MEASURE = """() => {
  const t = document.querySelector('#ai-oproepen table');
  const frame = (document.querySelector('#ai-oproepen [data-table-frame]') || t.parentElement).getBoundingClientRect();
  const head = name => [...t.querySelectorAll('thead th')].find(th => th.innerText.trim() === name);
  const shown = name => { const th = head(name); return !!th && th.getBoundingClientRect().width > 0; };
  const cost = [...t.querySelectorAll('tbody [data-cell=amount]')].map(td => td.getBoundingClientRect().right);
  const rows = [...t.querySelectorAll('tbody tr')].map(tr => Math.round(tr.getBoundingClientRect().height));
  return {frame: [Math.round(frame.left), Math.round(frame.right)], table: Math.round(t.getBoundingClientRect().width),
          costRight: Math.round(Math.max(...cost)), rows, model: shown('Model'), duur: shown('Duur'),
          scroll: document.documentElement.scrollWidth};
}"""


@pytest.mark.parametrize("width", [390, 1150, 1280, 1440])
def test_the_ai_log_reads_on_the_kit(calls, width):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as p:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = b.new_page(base_url=BASE, viewport={"width": width, "height": 1000})
        try:
            login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
            page.goto(PAGE)
            pagina_klaar(page)
            page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running')")
            m = page.evaluate(_MEASURE)
            print(f"MEASURE {width}: {m}")
            assert m["scroll"] == width, "the page scrolls sideways"
            assert m["costRight"] <= m["frame"][1], "the cost stands outside the frame"
            assert len(m["rows"]) >= len(CALLS)
            if width >= 1150:
                assert max(m["rows"]) <= 60, "a call keeps the row's 57 px on a wide screen"
                assert m["duur"], "the duration stands from 1 150 px"
            assert m["model"] == (width >= 1280), "Model · Provider stands on a wide screen only"
            folder = os.environ.get("E2E_PRINTS")
            if folder:
                os.makedirs(folder, exist_ok=True)
                table = page.locator("#ai-oproepen").bounding_box()
                y = max(0, table["y"] - 60)
                page.screenshot(
                    path=os.path.join(folder, f"1925-ai-log-{width}.png"),
                    clip={"x": 0, "y": y, "width": width, "height": 900},
                )
        finally:
            page.close()
            b.close()

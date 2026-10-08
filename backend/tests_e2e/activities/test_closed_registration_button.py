"""E2E: "Afgesloten" is a disabled button beside "Wie doet er mee?" (#1375).

An activity whose only component closed its registrations. On the public list at
390 and 1280 px, the closed state must be a button of the same height as "Wie doet
er mee?", on the same line, with a visible dark-grey border, and not clickable.

Proven red against master `3f3740c3`, with a server built from an export of it: at
both widths the closed state was a badge `<span>` 20 px high beside a button of 44
(390 px) or 26 (1280 px), without a border.
"""

import os
import secrets
import sys
from datetime import date, timedelta
from decimal import Decimal

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil  # noqa: E402

SHOTS = "/scratch/shots_1375"

_MEASURE = """(name) => {
  const card = [...document.querySelectorAll('article, .rounded-2xl, li')]
    .filter(el => el.textContent.includes(name))
    .sort((a, b) => a.textContent.length - b.textContent.length)[0];
  // The button, not the status label beside the title, which says "Afgesloten" too.
  // Where master showed a badge, fall back to that badge so the measurement says so.
  const closed = card.querySelector('button[disabled]')
    || [...card.querySelectorAll('span')].find(el => el.textContent.trim() === 'Inschrijvingen afgesloten');
  const who = [...card.querySelectorAll('button, a')]
    .find(el => el.textContent.trim().startsWith('Wie doet er mee?'));
  const box = el => { const r = el.getBoundingClientRect();
    return {top: Math.round(r.top), bottom: Math.round(r.bottom), height: Math.round(r.height),
            right: Math.round(r.right)}; };
  const style = getComputedStyle(closed);
  return {
    doc: document.documentElement.scrollWidth, vw: innerWidth,
    tag: closed.tagName.toLowerCase(), disabled: closed.disabled === true,
    text: closed.textContent.trim(),
    aria: closed.getAttribute('aria-disabled'),
    border_width: parseFloat(style.borderTopWidth), border_color: style.borderTopColor,
    closed: box(closed), who: box(who),
  };
}"""


def _closed_activity(name: str) -> None:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import (
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
    )

    db = SessionLocal()
    try:
        activity = Activity(name=name, location="Miloheem")
        db.add(activity)
        db.flush()
        db.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=60)))
        component = ActivitySubRegistration(
            activity_id=activity.id,
            name="Deelname",
            registration_type_code="INDIVIDUAL",
            registration_closes_on=date.today() - timedelta(days=2),
            price=Decimal("0"),
            is_free=True,
        )
        db.add(component)
        db.flush()
        db.add(
            ActivityProduct(
                component_id=component.id, name="Plaats", price=Decimal("0"), is_free=True
            )
        )
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


@pytest.mark.parametrize("width", [390, 1280])
def test_the_closed_state_is_a_disabled_button_in_line(browser, width):
    name = f"Afgesloten {secrets.token_hex(2)}"
    _closed_activity(name)
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        page.goto("/activiteiten")
        htmx_stil(page)
        page.get_by_text(name).first.scroll_into_view_if_needed()

        m = page.evaluate(_MEASURE, name)
        print(f"MEASURE @{width}", m)
        assert m["tag"] == "button" and m["disabled"] and m["aria"] == "true", m
        assert m["text"] == "Afgesloten", m
        assert m["closed"]["height"] == m["who"]["height"], f"@{width}: not the same height: {m}"
        assert abs(m["closed"]["top"] - m["who"]["top"]) <= 1, f"@{width}: not on one line: {m}"
        assert m["border_width"] >= 1, f"no visible border: {m}"
        assert m["doc"] <= m["vw"], m

        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.wait_for_function(
                "() => document.getAnimations().every(a => a.playState !== 'running')"
            )
            page.screenshot(path=f"{SHOTS}/{width}-afgesloten.png")
    finally:
        page.close()

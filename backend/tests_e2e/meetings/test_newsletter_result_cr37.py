"""E2E: the result of a sent newsletter (CR-37, #2027) at 390 and 1280 px.

Measured from the rendered DOM, not from the template:

- the *Resultaat* block of the archive: every part of it (the figures, the link list, the
  note) lies inside the card's left and right edge, a long address breaks inside the card,
  and the page does not scroll sideways;
- the archive list: the result line stands once on each sent letter and on no draft.

Prints of both screens are taken when `E2E_PRINT_DIR` is set (looked at by whoever hands
the work over). A sent letter with four deliveries, three counted events and a link of 150
characters is made for this file and removed again.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

from app.kernel.clock import belgian_today

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests._letter import letter_doc
from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

SHORT = "https://voorbeeld.example/agenda"
LONG = "https://voorbeeld.example/" + "een-lange-pagina-met-veel-woorden/" * 4 + "einde?a=1&b=2"
BLOCK = """() => {
  const card = document.querySelector('[data-letter-result]');
  const box = card.getBoundingClientRect();
  const parts = [...card.querySelectorAll('dl, ul, li, p, h2, h3')].map(e => {
    const r = e.getBoundingClientRect(); return { tag: e.tagName, left: Math.round(r.left), right: Math.round(r.right) };
  });
  return { card: [Math.round(box.left), Math.round(box.right)], parts,
    outside: parts.filter(p => p.left < Math.round(box.left) || p.right > Math.round(box.right)).length,
    links: card.querySelectorAll('[data-letter-links] li').length,
    page: [window.innerWidth, document.documentElement.scrollWidth] };
}"""
LIST = """() => ({
  lines: document.querySelectorAll('[data-letter-result]').length,
  cards: [...document.querySelectorAll('tr[data-letter]')].map(a => ({
    subject: a.querySelector('[data-row-link]').innerText.trim(), lines: a.querySelectorAll('[data-letter-result]').length })),
  page: [window.innerWidth, document.documentElement.scrollWidth] })"""


@pytest.fixture(scope="module")
def letters():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.newsletter.models import (
        Audience,
        Delivery,
        DeliveryKind,
        DeliveryStatus,
        LetterEvent,
        LetterLink,
        LetterStatus,
        Newsletter,
    )

    db = SessionLocal()
    try:
        sent = Newsletter(
            subject="E2E Resultaat",
            body_document=letter_doc("<div>Beste</div>"),
            audience=Audience.BOTH,
            status=LetterStatus.SENT,
            sent_body_html="<div>Beste</div>",
        )
        draft = Newsletter(subject="E2E Concept", body_document=letter_doc("<div>Beste</div>"))
        db.add_all([sent, draft])
        db.flush()
        for n in range(4):
            db.add(
                Delivery(
                    newsletter_id=sent.id,
                    email=f"lezer{n}@example.com",
                    kind=DeliveryKind.MEMBER,
                    status=DeliveryStatus.SENT,
                )
            )
        short = LetterLink(newsletter_id=sent.id, url=SHORT)
        long = LetterLink(newsletter_id=sent.id, url=LONG)
        db.add_all([short, long])
        db.flush()
        today = belgian_today()
        for code, link in (("a", None), ("b", None), ("a", short.id)):
            db.add(
                LetterEvent(
                    newsletter_id=sent.id, code=f"{sent.id}.{code}.x", link_id=link, day=today
                )
            )
        db.commit()
        ids = (sent.id, draft.id)
    finally:
        db.close()

    yield ids

    db = SessionLocal()
    try:
        for model in (LetterEvent, LetterLink, Delivery):
            db.query(model).filter(model.newsletter_id.in_(ids)).delete(synchronize_session=False)
        db.query(Newsletter).filter(Newsletter.id.in_(ids)).execution_options(
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
    page.set_viewport_size({"width": page.viewport_size["width"], "height": height})
    page.screenshot(path=os.path.join(folder, name), caret="initial")


def _open(browser, width, path):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    page.goto(path)
    pagina_klaar(page)
    return page


@pytest.mark.parametrize("width", [390, 1280])
def test_the_result_block_stays_inside_its_card(browser, letters, width):
    page = _open(browser, width, f"/admin/nieuwsbrieven/{letters[0]}")
    try:
        m = page.evaluate(BLOCK)
        print("MEASURE result block", width, m)
        assert m["parts"], "the block has parts"
        assert m["outside"] == 0, f"a part lies past the card: {m}"
        assert m["links"] == 2
        assert m["page"] == [width, width], "the page scrolls sideways"
        _print(page, f"archief-{width}.png")
    finally:
        page.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_the_list_has_one_result_line_per_sent_letter(browser, letters, width):
    page = _open(browser, width, "/admin/nieuwsbrieven")
    try:
        m = page.evaluate(LIST)
        print("MEASURE result line", width, m)
        mine = {c["subject"]: c["lines"] for c in m["cards"] if c["subject"].startswith("E2E")}
        assert mine == {"E2E Resultaat": 1, "E2E Concept": 0}, mine
        assert m["lines"] == sum(c["lines"] for c in m["cards"])
        assert m["page"] == [width, width], "the page scrolls sideways"
        _print(page, f"lijst-{width}.png")
    finally:
        page.close()

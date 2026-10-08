"""E2E #1380: the registration asks its questions in the form's own block.

Koen, testing the Sint registration on HDEV: the fields were the form builder's, but
everything around them was built again in `_inschrijf_velden.html` — no title, no
description, other spacing, no white card — so the work done on the form's own page
never reached the registration. Two places for one thing.

Measured on the rendered pages, at 390 and 1280 px: the standalone form
(`/formulier/…`) and the registration page of a component that asks the same form.
The form's title has the same size, weight and colour on both; two questions stand
the same distance apart; the questions sit in a white card; neither page is wider
than the screen.

Proven red against master `08a3ffbd` (30 September 2026): the registration page had
no form title at all (the block showed a small "Vragen" label).
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

TITLE = "Sint vragenblok"

MEASURE = """(title) => {
  const h = [...document.querySelectorAll('h1, h2')].find(e => e.innerText.trim() === title);
  const blocks = [...document.querySelectorAll('[data-field^="f"]')].filter(e => e.offsetParent);
  const card = blocks.length ? blocks[0].closest('[data-form-section]') : null;
  const label = blocks.length ? getComputedStyle(blocks[0].querySelector(':scope > label, :scope > p')) : null;
  const s = h ? getComputedStyle(h) : null;
  return {
    title: s ? {size: s.fontSize, weight: s.fontWeight, color: s.color} : null,
    gap: blocks.length > 1
      ? Math.round(blocks[1].getBoundingClientRect().top - blocks[0].getBoundingClientRect().bottom)
      : null,
    card: card ? getComputedStyle(card).backgroundColor : null,
    label: label ? {size: label.fontSize, weight: label.fontWeight, color: label.color} : null,
    doc: document.documentElement.scrollWidth, vw: innerWidth,
  };
}"""


@pytest.fixture(scope="module")
def setup():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from tests.conftest import ask_questions, seed_activity_with_product, seed_question_form

    db = SessionLocal()
    activity, component, _product = seed_activity_with_product(db, price="0", is_free=True)
    form = seed_question_form(db, title=TITLE)
    form.description = "Voor de Sint: vul dit samen met je kinderen in."
    db.commit()
    ask_questions(db, component, form.id)
    out = {
        "form": f"/formulier/{form.share_token}",
        "registration": f"/activiteiten/{activity.id}/inschrijven/{component.id}",
    }
    db.close()
    return out


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _measure(browser, path: str, width: int) -> dict:
    context = browser.new_context(base_url=BASE, viewport={"width": width, "height": 900})
    page = context.new_page()
    try:
        page.goto(path)
        pagina_klaar(page)
        return page.evaluate(MEASURE, TITLE)
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_the_registration_asks_in_the_forms_own_block(browser, setup, width):
    form = _measure(browser, setup["form"], width)
    reg = _measure(browser, setup["registration"], width)

    # #1589 (§2.6): the form's name stands in the name card of its own page; the
    # registration asks under its own section "Vragen bij de inschrijving". What
    # the two share is the question cards — the same label, distance and card.
    assert form["title"] is not None, f"the form's own page lost its title: {form}"
    assert reg["title"] is None, "the registration page repeats the form's title"
    assert form["label"] is not None and reg["label"] == form["label"], (form, reg)
    assert reg["gap"] == form["gap"], f"gap between two questions @{width}: {form} — {reg}"
    assert reg["card"] == form["card"] == "rgb(255, 255, 255)", (form, reg)
    assert form["doc"] == form["vw"] and reg["doc"] == reg["vw"], (form, reg)

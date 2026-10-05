"""E2E: the public forms share one width, one surface scale and one button
hierarchy — AC5 of CR-11, measured (#1591, pilot B, P4; end state §2.6).

A DOM comparison over the public form pages, at 390 and 1 440 px: for each page
the column's width, the cards' radius, padding and background, the distance
between two cards, and the primary button's background, radius, height and
font. The values must be the SAME on every page — that is the acceptance — and
they are pinned to the norm once (768 / 358 px, 14 px radius, 16 px padding,
32 px between cards), so "the same" cannot become "equally wrong".

`PAGES` holds what stands on master: register and a public form (P2, #1589).
Word lid, renew and Mijn gezin join it with P3 (#1590) — add their address
here, nothing else.

Proven red (run, restored): `rounded-2xl` replaced by `rounded-lg` in
`ui.flow_card` → the public form's name card differs from its section cards
("its cards differ", 6 px against 14 px); `p-4` replaced by `p-6` in
`ui.section` → every page is equal and all four tests fail on the norm and on
the name card.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

#: width → what the norm says (§2.6): column, card radius, card padding, gap.
NORM = {390: (358, "14px", "16px", 32), 1440: (768, "14px", "16px", 32)}

MEASURE = """() => {
  const px = n => Math.round(n);
  const frame = document.querySelector('[data-public-form-page]');
  const cards = [...frame.querySelectorAll('[data-form-section]')].filter(c => c.checkVisibility());
  const style = c => { const s = getComputedStyle(c); return [s.borderTopLeftRadius, s.paddingLeft, s.backgroundColor, s.borderTopWidth].join(' | '); };
  const gaps = cards.slice(1).map((c, i) => px(c.getBoundingClientRect().top - cards[i].getBoundingClientRect().bottom));
  const save = document.querySelector('[data-form-save]');
  const b = getComputedStyle(save);
  return {
    column: px(frame.getBoundingClientRect().width),
    cards: cards.length,
    card_styles: [...new Set(cards.map(style))],
    gaps: [...new Set(gaps)],
    button: [b.backgroundColor, b.color, b.borderTopLeftRadius, px(save.getBoundingClientRect().height) + 'px', b.fontSize, b.fontWeight].join(' | '),
    button_class: save.className.split(/\\s+/).filter(c => /^(bg-|text-white|font-|rounded)/.test(c)).sort().join(' '),
  };
}"""


@pytest.fixture(scope="module")
def pages():
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from tests.conftest import seed_activity_with_product, seed_question_form

    db = SessionLocal()
    activity, component, _product = seed_activity_with_product(db, price="10.00", is_free=False)
    form = seed_question_form(db, title="E2E één kader", sections=2)
    db.commit()
    #: name → address. P3 adds: Word lid, renew, Mijn gezin.
    found = {
        "register": f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        "public form": f"/formulier/{form.share_token}",
    }
    db.close()
    return found


@pytest.fixture(scope="module")
def measured(pages):
    out: dict[int, dict[str, dict]] = {}
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        for width, height in ((390, 844), (1440, 900)):
            page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
            out[width] = {}
            for name, path in pages.items():
                page.goto(path)
                pagina_klaar(page)
                out[width][name] = page.evaluate(MEASURE)
            page.close()
        browser.close()
    print("MEASURE AC5", out)
    return out


@pytest.mark.parametrize("width", [390, 1440])
def test_every_public_form_has_the_same_frame(measured, width):
    per_page = measured[width]
    assert len(per_page) >= 2, "one page is always equal to itself"
    for name, m in per_page.items():
        assert m["cards"] >= 3, f"{name}: the measurement found {m['cards']} cards"
        assert len(m["card_styles"]) == 1, f"{name} @{width}: its cards differ: {m['card_styles']}"
        assert len(m["gaps"]) == 1, f"{name} @{width}: its cards are not evenly apart: {m['gaps']}"
    for key in ("column", "card_styles", "gaps", "button", "button_class"):
        values = {name: m[key] for name, m in per_page.items()}
        distinct = {str(v) for v in values.values()}
        assert len(distinct) == 1, f"@{width} the pages differ in {key}: {values}"


@pytest.mark.parametrize("width", [390, 1440])
def test_that_frame_is_the_norms(measured, width):
    column, radius, padding, gap = NORM[width]
    m = next(iter(measured[width].values()))
    assert m["column"] == column, m["column"]
    card_radius, card_padding, background, _border = m["card_styles"][0].split(" | ")
    assert (card_radius, card_padding) == (radius, padding), m["card_styles"]
    assert background == "rgb(255, 255, 255)", background
    assert m["gaps"] == [gap], m["gaps"]
    # The primary is the brand's filled button in both shells: white on a colour.
    fill, ink = m["button"].split(" | ")[:2]
    assert ink == "rgb(255, 255, 255)" and fill != ink, m["button"]

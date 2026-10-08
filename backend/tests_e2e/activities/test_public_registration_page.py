"""E2E: the registration page on the public form page (#1589, CR-11 pilot B, P2;
`docs/design-system-end-state.md` §2.6).

What a server test cannot see:

- **the frame**: a column of 768 px centred at 1 440 (x 336), 720 px at 768,
  358 px at 390; the title 40 / 32 px; the first field inside the first screen
  on a phone; nothing scrolls sideways;
- **the counter** is 44 px at every width;
- **the action bar**: 64 px at 1 440 with the primary at the right and
  *Annuleren* as text; 121 px on a phone with a button of 358 × 44 px;
- **the bell** sits 16 px above the visible bar on a phone and returns to the
  bottom edge when the bar is out of view;
- **the button follows the payment choice**: "Inschrijven en betalen" with
  *Online betalen*, "Inschrijven" with *Overschrijving*;
- **"Later"** hides the questions and says where the link comes;
- **a refusal** keeps what was typed: the banner names the fields, each refused
  field gets its reason and a red border, the focus goes to the first;
- **leaving with changes** asks "Deze pagina verlaten?" and *Blijven* keeps
  the page; a good save leaves without a question;
- **the same cards** on the board's page, in the admin shell.

Proven red (each on this branch, restored after):
- `margin-inline:auto` taken off `.public-form-page` → the frame test fails
  (x 96 at 1 440);
- `touch=True` taken off the product row → the frame test fails at 768 and
  1 440 (36 px), and so does the board's page;
- the bell's `--bell-bottom` no longer set (`placeBell` returns at once) → the
  bell test fails (the bell lies over the bar);
- the `x-text` taken off the button's label → the label test fails;
- `record-form.js` not loaded by `site_base.html` → the refusal test (no field
  is marked) and the leave test (no question) fail.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, login_met_sessie, pagina_klaar  # noqa: E402

_BOXES = """() => {
  const box = e => { if (!e || !e.checkVisibility()) return null; const r = e.getBoundingClientRect();
    return {x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), r: Math.round(r.right), b: Math.round(r.bottom)}; };
  const q = s => document.querySelector(s);
  return {
    page: box(q('[data-public-form-page]')), title: parseFloat(getComputedStyle(q('[data-public-form-page] h1')).fontSize),
    first: box(q('#contact_name')), bar: box(q('[data-action-bar]')), save: box(q('[data-form-save]')),
    cancel: box(q('[data-form-cancel]')), bell: box(q('[data-raakje-bell]')),
    counter: [...document.querySelectorAll('[data-product-row] button')].map(b => Math.round(b.getBoundingClientRect().height)),
    cards: document.querySelectorAll('[data-form-flow] [data-form-section]').length,
    heads: [...document.querySelectorAll('[data-form-flow] [data-form-section] > h2')].map(h => h.textContent.trim()),
    legend: [...document.querySelectorAll('#main *')].filter(e => e.children.length === 0 && /Verplicht veld/.test(e.textContent)).length,
    scroll: document.documentElement.scrollWidth, width: innerWidth, height: innerHeight,
  };
}"""

_TWO_FRAMES = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


@pytest.fixture(scope="module")
def setup():
    """A paid activity with one product, one with the component's questions, and
    a board member."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole
    from tests.conftest import seed_activity_with_product, seed_question_form

    db = SessionLocal()
    activity, component, product = seed_activity_with_product(db, price="10.00", is_free=False)
    asked, asking, asked_product = seed_activity_with_product(db, price="5.00", is_free=False)
    asking.form_id = seed_question_form(db, title=f"Vragen {secrets.token_hex(2)}").id
    email = f"e2e-1589-{secrets.token_hex(3)}@example.org"
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    out = {
        "url": f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        "board": f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw",
        "asking": f"/activiteiten/{asked.id}/inschrijven/{asking.id}",
        "product": product.id,
        "asked_product": asked_product.id,
        "session": make_session_value(email),
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


def _open(browser, path, width, height=900, session=None):
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    if session:
        login_met_sessie(page, session)
    page.goto(path)
    pagina_klaar(page)
    page.wait_for_function("() => !!window.raakRecordForm && window.raakRecordForm.ready()")
    page.evaluate(_TWO_FRAMES)
    return page


@pytest.mark.parametrize(
    "width,height,column,x,title",
    [(390, 844, 358, 16, 32), (768, 900, 720, 24, 40), (1440, 900, 768, 336, 40)],
)
def test_the_frame_is_one_centred_column(browser, setup, width, height, column, x, title):
    page = _open(browser, setup["url"], width, height)
    m = page.evaluate(_BOXES)
    page.close()
    assert (m["page"]["w"], m["page"]["x"]) == (column, x), m["page"]
    assert m["title"] == title
    assert m["scroll"] == width, "the page scrolls sideways"
    assert m["heads"] == ["Contact", "Je deelname", "Betalen"], m["heads"]
    assert m["legend"] == 0, "a '* Verplicht veld' legend stands on the page"
    # The first field stands inside the first screen, under the head.
    assert m["first"]["b"] < height - (121 if width < 768 else 64), m["first"]
    # 44 px at every width: the counter keeps its touch size on a desktop.
    assert m["counter"] and set(m["counter"]) == {44}, m["counter"]


def test_the_action_bar_on_a_desktop_and_on_a_phone(browser, setup):
    page = _open(browser, setup["url"], 1440)
    wide = page.evaluate(_BOXES)
    page.close()
    assert wide["bar"]["h"] == 64 and (wide["bar"]["x"], wide["bar"]["w"]) == (336, 768), wide[
        "bar"
    ]
    assert wide["save"]["r"] == wide["bar"]["r"] - 16, "the primary does not stand at the right"
    assert wide["cancel"]["r"] < wide["save"]["x"], "Annuleren does not stand left of the primary"

    page = _open(browser, setup["url"], 390, 844)
    phone = page.evaluate(_BOXES)
    assert phone["bar"]["h"] == 121 and (phone["bar"]["x"], phone["bar"]["w"]) == (0, 390), phone[
        "bar"
    ]
    assert (phone["save"]["w"], phone["save"]["h"]) == (358, 44), phone["save"]
    assert phone["bar"]["b"] == 844, "the bar does not stand at the window's bottom"
    page.close()


def test_the_bell_sits_above_the_visible_bar_on_a_phone(browser, setup):
    page = _open(browser, setup["url"], 390, 844)
    m = page.evaluate(_BOXES)
    if m["bell"] is None:
        page.close()
        pytest.skip("the assistant is off on this site: no bell")
    assert m["bell"]["b"] == m["bar"]["y"] - 16, (m["bell"], m["bar"])
    # No part of the bar lies under the bell.
    assert m["bell"]["b"] <= m["bar"]["y"]
    # Out of the form: the bar leaves the window and the bell returns.
    page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
    page.wait_for_function(
        "() => { const r = document.querySelector('[data-raakje-bell]').getBoundingClientRect();"
        " return Math.round(innerHeight - r.bottom) === 16; }"
    )
    page.close()


def test_the_button_names_the_next_step(browser, setup):
    page = _open(browser, setup["url"], 390, 844)
    label = page.locator("[data-save-idle]")
    expect(label).to_have_text("Inschrijven en betalen")
    assert page.locator('input[name="payment_method"][value="online"]').is_checked()
    page.locator('input[name="payment_method"][value="transfer"]').check()
    expect(label).to_have_text("Inschrijven")
    page.locator('input[name="payment_method"][value="online"]').check()
    expect(label).to_have_text("Inschrijven en betalen")
    # Nothing to pay: nothing to pay for, whatever the choice.
    with page.expect_response(lambda r: r.url.endswith("/totaal")):
        page.fill(f"#product-{setup['product']}", "0")
        page.locator(f"#product-{setup['product']}").dispatch_event("change")
    htmx_stil(page)
    expect(label).to_have_text("Inschrijven")
    page.close()


def test_later_hides_the_questions(browser, setup):
    page = _open(browser, setup["asking"], 390, 844)
    questions = page.locator("#inschrijf-vragen")
    expect(questions).to_be_visible()
    expect(page.locator("[data-questions-later]")).to_be_hidden()
    page.locator('input[name="questions"][value="later"]').check()
    expect(questions).to_be_hidden()
    expect(page.locator("[data-questions-later]")).to_be_visible()
    page.locator('input[name="questions"][value="now"]').check()
    expect(questions).to_be_visible()
    page.close()


def test_a_refusal_marks_the_fields_and_keeps_what_was_typed(browser, setup):
    page = _open(browser, setup["url"], 390, 844)
    page.fill("#phone", "0470000000")
    page.fill("#remarks", "Blijft staan")
    page.click("[data-form-save]")
    banner = page.locator("[data-save-refusal]")
    expect(banner).to_contain_text("Verzenden kan nog niet: controleer 2 velden.")
    expect(banner).to_contain_text("Je andere wijzigingen zijn behouden.")
    assert banner.locator("[data-error-for]").count() == 2
    # The marks come when the banner has settled, a moment after it shows.
    expect(page.locator("[data-refused]")).to_have_count(2)
    marked = page.evaluate(
        "() => [...document.querySelectorAll('[data-refused]')].map(e => [e.dataset.field,"
        " e.querySelector('[data-refused-message]').textContent,"
        " getComputedStyle(e.querySelector('input')).borderTopColor,"
        " e.querySelector('input').getAttribute('aria-invalid'),"
        " getComputedStyle(e.querySelector('label')).color])"
    )
    assert [m[0] for m in marked] == ["contact_name", "contact_email"], marked
    assert marked[0][1] == "Vul je naam in." and marked[1][1] == "Vul een geldig e-mailadres in."
    ink = page.evaluate("() => getComputedStyle(document.querySelector('label[for=phone]')).color")
    for _field, _text, border, invalid, label in marked:
        assert invalid == "true"
        assert border != page.evaluate(
            "() => getComputedStyle(document.querySelector('#phone')).borderTopColor"
        )
        assert label == ink, "a refused field's label changed colour"
    assert page.evaluate("() => document.activeElement.id") == "contact_name"
    # Everything typed is still there; the button is itself again.
    assert page.input_value("#phone") == "0470000000"
    assert page.input_value("#remarks") == "Blijft staan"
    expect(page.locator("[data-save-idle]")).to_be_visible()
    # A link of the banner brings the focus to its field.
    banner.locator('[data-error-for="contact_email"]').click()
    assert page.evaluate("() => document.activeElement.id") == "contact_email"
    page.close()


def test_leaving_with_changes_asks_and_a_good_save_does_not(browser, setup):
    page = _open(browser, setup["url"], 1440)
    naam = f"Verlater {secrets.token_hex(2)}"
    page.fill("#contact_name", naam)
    page.click("[data-form-cancel]")
    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("Wijzigingen weggooien?")
    dialog.get_by_role("button", name="Verder bewerken").click()
    assert page.input_value("#contact_name") == naam
    page.locator("#site-nav-breed a").first.click()
    expect(dialog).to_contain_text("Deze pagina verlaten?")
    dialog.get_by_role("button", name="Blijven").click()
    assert page.url.endswith(setup["url"])
    # A good save leaves without a question: the confirmation takes the page.
    page.fill("#contact_email", "verlater-e2e@example.org")
    page.fill("#phone", "0470000000")
    page.locator('input[name="payment_method"][value="transfer"]').check()
    page.click("[data-form-save]")
    head = page.locator("[data-public-form-page][data-result] h1")
    expect(head).to_have_text("Je inschrijving is ontvangen")
    expect(page.locator("[data-payment-pending]")).to_contain_text("Betaling nog af te ronden")
    expect(page.locator("[data-payment-pending]")).to_contain_text("€ 10,00")
    assert page.locator("form[data-record-form]").count() == 0
    page.close()


def test_the_board_page_shows_the_same_cards(browser, setup):
    public = _open(browser, setup["url"], 1440)
    theirs = public.evaluate(_BOXES)
    public.close()
    page = _open(browser, setup["board"], 1440, session=setup["session"])
    ours = page.evaluate(_BOXES)
    assert ours["heads"] == theirs["heads"] == ["Contact", "Je deelname", "Betalen"]
    assert ours["page"]["w"] == 768 and ours["bar"]["h"] == 64
    assert set(ours["counter"]) == {44}
    expect(page.locator("[data-save-idle]")).to_have_text("Inschrijving toevoegen")
    # The board registers for somebody else: no member nudge.
    assert page.locator("[data-member-nudge]").count() == 0
    page.close()

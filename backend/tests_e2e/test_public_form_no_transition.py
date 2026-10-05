"""E2E: a refusal, a recalculated total and the payment status arrive on ONE
layer — without a view transition (Refs #1589).

The public shell runs a view transition on every htmx swap
(`globalViewTransitions`). That is right for a navigation and wrong for a swap
inside the page. Measured on the merged #1589 (5 October 2026): after a refused
registration the whole page cross-faded for 250 ms (16 frames) while the form
scrolled to its first refused field — the screenshot of that moment showed the
old page through the new one, and a person sees it as a quarter second of
double print. The same ran on every change of a quantity, where a click during
the transition does not land (the lesson of K8, #1562).

Each test watches every frame for an animation on a `::view-transition`
pseudo-element from just before the act until the result stands
(`schermen.watch_transitions`), and demands none. The refusal of a record in
the back office has the same test in `test_record_form.py`. Seeing the result is asserted first: "no transition" is also true of a
swap that never came.

Proven red (each on this branch, restored after): `transition:false` taken off
the `HX-Reswap` of `app.ui.refusal_response` → the two refusal tests fail
(16 and 17 frames); taken off the total's `hx-swap` in
`_inschrijf_prijsblok.html` → the total test fails.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (  # noqa: E402
    BASE,
    htmx_stil,
    pagina_klaar,
    transition_frames,
    watch_transitions,
)


@pytest.fixture(scope="module")
def setup():
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from tests.conftest import seed_activity_with_product, seed_question_form

    db = SessionLocal()
    activity, component, _product = seed_activity_with_product(db, price="10.00", is_free=False)
    form = seed_question_form(db, title="E2E één laag")
    db.commit()
    out = {
        "register": f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        "form": f"/formulier/{form.share_token}",
    }
    db.close()
    return out


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        yield p
        browser.close()


def _open(page, path):
    page.goto(path)
    pagina_klaar(page)
    page.wait_for_function("() => !!window.raakRecordForm && window.raakRecordForm.ready()")
    watch_transitions(page)


@pytest.mark.parametrize("which", ["register", "form"])
def test_a_refusal_arrives_without_a_transition(page, setup, which):
    _open(page, setup[which])
    page.click("[data-form-save]")
    expect(page.locator("[data-save-refusal]")).to_be_visible()
    expect(page.locator("[data-refused]").first).to_be_visible()
    assert transition_frames(page) == 0, "the page cross-fades when the banner arrives"


def test_a_recalculated_total_arrives_without_a_transition(page, setup):
    _open(page, setup["register"])
    total = page.locator("[data-total]")
    expect(total).to_contain_text("10,00")
    with page.expect_response(lambda r: r.url.endswith("/totaal")):
        page.locator("[data-product-row] button").last.click()
    htmx_stil(page)
    expect(total).to_contain_text("20,00")
    assert transition_frames(page) == 0, "the page cross-fades when the total follows a quantity"

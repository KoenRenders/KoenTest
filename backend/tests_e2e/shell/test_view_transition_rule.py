"""E2E: a view transition runs for a navigation and for nothing else (#1591).

Both shells switch view transitions on for every htmx swap
(`globalViewTransitions`). That is right when the page becomes another page,
and wrong for a swap inside a page: the whole document cross-fades for 250 ms,
a click in that time does not land, and when the page scrolls meanwhile the old
state shows through the new one (the double print on the refusal screenshots of
#1589). Counted over the whole e2e suite on 5 October 2026: 258 swaps ran a
transition, 89 of them a boosted navigation and 169 a swap inside a page.

The rule stands once, in the kit's shared script (`ui.htmx_ux`): a transition
only for a boosted request or a swap that updates the address. This file holds
one test per shape of swap that lost its transition, and two for what keeps it
— the rule may not quietly switch everything off:

| shape | here | on |
|---|---|---|
| 1 a refusal (422) | a banner into the message line; the body again | register, a public form; the organisation (`test_a_refusal_shows_its_reason.py`), the record (`test_record_form.py`) |
| 2 a recalculation while typing | the total | register |
| 3 a search while typing, no address | the circle's candidates | `test_vergaderkring_focus.py` |
| 4 a swap at load | the Assistent's button | the admin shell |
| 5 a row added | a member of the family | Word lid |
| 6 a command that redraws a part | a payment confirmed | `test_betalingen_tab_houdt_scope.py` |
| 8 a good answer that takes the page | the confirmation | register |
| **keeps it:** 7 a list's sort (updates the address) | | Betalingen |
| **keeps it:** a record saved (edit → read: the address changes) | measured, 13 frames | the activity |
| **keeps it:** a boosted navigation | | the admin's menu |

Each test asserts FIRST that the result of the act stands — zero frames is also
the answer of a swap that never came — and then reads the frames in which a
`::view-transition` animation ran since just before the act
(`schermen.watch_transitions`).

Proven red (each on this branch, restored after): the listener on
`htmx:beforeTransition` taken out of `ui.htmx_ux` → every "without" test here
fails with 13–17 frames (and the three in the other files); the listener made
to cancel ALWAYS → the two "keeps" tests fail with 0 frames.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (  # noqa: E402
    BASE,
    htmx_afgerond,
    htmx_stil,
    login_met_sessie,
    pagina_klaar,
    transition_frames,
    watch_transitions,
    watch_transitions_from_load,
)


@pytest.fixture(scope="module")
def setup():
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.auth.api import make_session_value
    from app.domains.auth.models import User, UserRole
    from tests.conftest import seed_activity_with_product, seed_question_form

    db = SessionLocal()
    activity, component, _product = seed_activity_with_product(db, price="10.00", is_free=False)
    form = seed_question_form(db, title="E2E één laag")
    email = f"e2e-1591-{secrets.token_hex(3)}@example.org"
    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code="FINANCE"))
    db.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db.commit()
    out = {
        "register": f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        "form": f"/formulier/{form.share_token}",
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


@pytest.fixture
def page(browser):
    p = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    yield p
    p.close()


@pytest.fixture
def admin(browser, setup):
    p = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    login_met_sessie(p, setup["session"])
    yield p
    p.close()


def _open_form(page, path):
    page.goto(path)
    pagina_klaar(page)
    page.wait_for_function("() => !!window.raakRecordForm && window.raakRecordForm.ready()")
    watch_transitions(page)


# ── What lost its transition ─────────────────────────────────────────────────


@pytest.mark.parametrize("which", ["register", "form"])
def test_a_refusal_arrives_without_a_transition(page, setup, which):
    _open_form(page, setup[which])
    page.click("[data-form-save]")
    expect(page.locator("[data-save-refusal]")).to_be_visible()
    expect(page.locator("[data-refused]").first).to_be_visible()
    assert transition_frames(page) == 0, "the page cross-fades when the banner arrives"


def test_a_recalculated_total_arrives_without_a_transition(page, setup):
    _open_form(page, setup["register"])
    total = page.locator("[data-total]")
    expect(total).to_contain_text("10,00")
    with page.expect_response(lambda r: r.url.endswith("/totaal")):
        page.locator("[data-product-row] button").last.click()
    htmx_stil(page)
    expect(total).to_contain_text("20,00")
    assert transition_frames(page) == 0, "the page cross-fades when the total follows a quantity"


def test_a_confirmation_takes_the_page_without_a_transition(page, setup):
    _open_form(page, setup["register"])
    page.fill("#contact_name", "Zonder Overgang")
    page.fill("#contact_email", "zonder-overgang@example.org")
    page.fill("#phone", "0470000000")
    page.locator('input[name="payment_method"][value="transfer"]').check()
    page.click("[data-form-save]")
    expect(page.locator("[data-public-form-page][data-result] h1")).to_have_text(
        "Je inschrijving is ontvangen"
    )
    assert transition_frames(page) == 0, "the confirmation cross-fades in"


def test_a_row_added_arrives_without_a_transition(admin):
    """On the board's "new member" page: since #1590 the public Word lid page adds
    its rows in the page (the kit's repeating group, no request), so the row that
    still arrives through htmx is the board's."""
    admin.goto("/admin/leden/nieuw")
    pagina_klaar(admin)
    rows = admin.locator('[id^="persoon-rij-"]')
    before = rows.count()
    watch_transitions(admin)
    with htmx_afgerond(admin):
        admin.locator('[hx-get="/admin/leden/nieuw/persoon-rij"]').click()
    expect(rows).to_have_count(before + 1)
    assert transition_frames(admin) == 0, "the page cross-fades when a row is added"


def test_a_swap_at_load_runs_no_transition(browser, setup):
    """The Assistent's button loads itself into the top bar (K8, #1562) — the
    first swap that had to carry `transition:false`. Counted from the page's
    very start, because the swap comes before anything can be watched."""
    p = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    login_met_sessie(p, setup["session"])
    watch_transitions_from_load(p)
    p.goto("/admin/betalingen")
    pagina_klaar(p)
    p.wait_for_function(
        "() => { const b = document.querySelector('#assistent-knop');"
        " return !!b && !b.matches('[hx-trigger=load]'); }"
    )
    frames = transition_frames(p)
    p.close()
    assert frames == 0, "a swap at load cross-fades the page that just arrived"


# ── What keeps it ────────────────────────────────────────────────────────────


def test_a_sort_that_updates_the_address_keeps_its_transition(admin):
    admin.goto("/admin/betalingen")
    pagina_klaar(admin)
    watch_transitions(admin)
    with htmx_afgerond(admin):
        admin.locator("#betalingen-lijst a[data-sort=naam]").click()
    assert "sort=naam" in admin.url
    assert transition_frames(admin) > 0, "the rule switched off the transition of a list's sort"


def test_a_boosted_navigation_keeps_its_transition(admin):
    admin.goto("/admin/betalingen")
    pagina_klaar(admin)
    watch_transitions(admin)
    admin.locator(
        '#main-nav a[href="/admin/activiteiten"], nav a[href="/admin/activiteiten"]'
    ).first.click()
    admin.wait_for_url("**/admin/activiteiten")
    pagina_klaar(admin)
    assert transition_frames(admin) > 0, "the rule switched off the transition of a navigation"

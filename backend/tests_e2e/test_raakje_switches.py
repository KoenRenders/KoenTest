"""E2E: the two Raakje switches of a tenant, in a browser (#1568).

A switch is a checkbox the kit dresses up, and "off" is the case a server test
cannot prove by posting what it thinks a browser sends: an unticked checkbox
sends nothing, so without the hidden field of `ui.switch` the save would keep
the old value and the screen would show the switch back on.

- The Assistent card of the tenant editor holds two switches, the knob at the
  left and the label at its right.
- Switching "Raakje op de publieke site" off and saving takes the bell off the
  tenant's public site; "Raakje in de backoffice" keeps its own state.
- Switching it on again brings the bell back. The test leaves the tenant as it
  found it.

Proven red (on this branch, restored after): the hidden field taken out of
`ui.switch` → after saving "off" the switch is still on and the bell still
there.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, PLATFORM, login_met_sessie, pagina_klaar  # noqa: E402

PUBLIC = "input[role=switch][name=public_chat_enabled]"
BACK_OFFICE = "input[role=switch][name=admin_chat_enabled]"
BELL = "#raakje-widget-gesprek"


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = b.new_page(viewport={"width": 1440, "height": 900})
        login_met_sessie(p, make_session_value(SEEDED_ADMIN_EMAIL), PLATFORM)
        yield p
        b.close()


def _editor(page) -> str:
    page.goto(PLATFORM + "/admin/tenants")
    pagina_klaar(page)
    href = (
        page.locator("a[href^='/admin/tenants/']:not([href$='/nieuw'])")
        .filter(has_text="Raak Millegem")
        .first.get_attribute("href")
    )
    return PLATFORM + href


def _open(page, editor: str) -> None:
    page.goto(editor)
    pagina_klaar(page)


def _save(page, editor: str, *, public: bool) -> None:
    _open(page, editor)
    label = page.locator(f"label:has({PUBLIC})")
    if page.locator(PUBLIC).is_checked() != public:
        label.click()
    assert page.locator(PUBLIC).is_checked() == public
    with page.expect_response(lambda r: r.request.method == "POST" and "/admin/tenants/" in r.url):
        page.locator("button[type=submit][form=tn-form]").first.click()
    pagina_klaar(page)


def _bell_on_the_site(page) -> bool:
    page.goto(BASE + "/")
    pagina_klaar(page)
    return page.locator(BELL).count() == 1


def test_the_card_holds_two_switches_knob_left_label_right(page):
    _open(page, _editor(page))
    card = page.locator("[data-card=chatbot]")
    assert card.locator("input[role=switch]").count() == 2
    for name, label in (
        ("admin_chat_enabled", "Raakje in de backoffice"),
        ("public_chat_enabled", "Raakje op de publieke site"),
    ):
        box = card.locator(f"label:has(input[name={name}])")
        m = box.evaluate(
            """l => { const k = l.querySelector('span[aria-hidden]').getBoundingClientRect();
                      const t = l.querySelector('span:not([aria-hidden])').getBoundingClientRect();
                      return {knob: [k.left, k.right, k.top + k.height / 2],
                              text: [t.left, t.top + t.height / 2], label: l.innerText.trim()}; }"""
        )
        print("MEASURE", name, m)
        assert m["label"] == label
        assert m["text"][0] - m["knob"][1] == 8, "the label stands 8 px right of the knob"
        assert abs(m["knob"][2] - m["text"][1]) <= 1, "knob and label share a centre line"


def test_public_off_takes_the_bell_off_the_site_and_on_brings_it_back(page):
    editor = _editor(page)
    _open(page, editor)
    was_on = page.locator(PUBLIC).is_checked()
    back_office = page.locator(BACK_OFFICE).is_checked()
    try:
        _save(page, editor, public=False)
        _open(page, editor)
        assert not page.locator(PUBLIC).is_checked(), "the saved 'off' did not stick"
        assert page.locator(BACK_OFFICE).is_checked() == back_office, "the two are not independent"
        assert not _bell_on_the_site(page), "the bell is still on the public site"

        _save(page, editor, public=True)
        _open(page, editor)
        assert page.locator(PUBLIC).is_checked()
        assert _bell_on_the_site(page), "the bell did not come back"
    finally:
        _save(page, editor, public=was_on)

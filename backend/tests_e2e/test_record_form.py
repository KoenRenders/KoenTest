"""E2E: the action bar and every state of a save (CR-11 block 9, #1561).

In a real browser, because every state here is what the page does with an
answer — or before there is one (design-system-end-state §3.6, §3.18):

- the bar: 64 px under the form's last section, sticky 16 px above the window's
  bottom while the form is longer than the window; on a phone 121 px at the
  window's bottom with Opslaan on the first line, and the last field reachable;
- a refusal: the banner names every field, each refused field carries its
  reason, the first has the focus, every typed value is still there;
- a removed row that may not go comes back with the reason on it;
- Annuleren with changes asks, and the filled, focused button is the safe one;
  leaving by a link asks too, and "Weggooien" performs the click;
- Verwijderen names the record and its consequence; a state command asks with
  its consequence, then says it happened and the badge changed;
- a failed save says so in the form, not in a toast; a saved one shows the
  toast and read mode;
- Ctrl+S saves; Esc closes a dialog and leaves the form.

Screenshots go outside the repo.
"""

import os
import sys
from datetime import date, timedelta

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (  # noqa: E402
    BASE,
    htmx_afgerond,
    login_met_sessie,
    pagina_klaar,
    transition_frames,
    watch_transitions,
)

NAME = "Balktest met inschrijving"
COMPONENT = "Avondwandeling"


def _seed() -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import (
        Activity,
        ActivityDate,
        ActivitySubRegistration,
        Registration,
    )

    db = SessionLocal()
    try:
        existing = db.query(Activity).filter(Activity.name == NAME).first()
        if existing is not None:
            return existing.id
        activity = Activity(name=NAME, location="Parochiezaal", description="Samen op pad.")
        db.add(activity)
        db.flush()
        db.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=90)))
        component = ActivitySubRegistration(
            activity_id=activity.id,
            name=COMPONENT,
            registration_type_code="INDIVIDUAL",
            price=0,
            is_free=True,
            max_participants=20,
            sort_order=0,
        )
        db.add(component)
        db.flush()
        db.add(
            Registration(
                activity_id=activity.id,
                component_id=component.id,
                registration_type="INDIVIDUAL",
                contact_name="An Voorbeeld",
                contact_email="an@example.com",
            )
        )
        db.commit()
        return activity.id
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity_id = _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), activity_id
        b.close()


def _page(setup, width: int = 1440, edit: bool = True, height: int | None = None):
    b, session, activity_id = setup
    page = b.new_page(
        base_url=BASE,
        viewport={"width": width, "height": height or (844 if width < 768 else 900)},
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    login_met_sessie(page, session)
    page.goto(f"/admin/activiteiten/{activity_id}" + ("?bewerken=1" if edit else ""))
    pagina_klaar(page)
    if edit:
        # Not "is not dirty": before its first state is taken the form is never
        # dirty, and a fill that came first would become that first state.
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
    return page


BAR = "[data-action-bar]"
DIALOG = "[data-dialog]"

_BAR = """() => {
  const r = e => { const b = e.getBoundingClientRect(); return {x: Math.round(b.left), y: Math.round(b.top), w: Math.round(b.width), h: Math.round(b.height), bottom: Math.round(b.bottom)}; };
  const bar = document.querySelector('[data-action-bar]');
  const q = s => bar.querySelector(s);
  return {window: [innerWidth, innerHeight], page: document.documentElement.scrollWidth, scroll: Math.round(scrollY),
          max_scroll: document.documentElement.scrollHeight - innerHeight,
          bar: r(bar), position: getComputedStyle(bar).position, background: getComputedStyle(bar).backgroundColor,
          column: r(document.querySelector('[data-form-column]')),
          save: r(q('[data-form-save]')), cancel: r(q('[data-form-cancel]')), remove: r(q('[data-form-delete]')),
          rare: r(document.querySelector('[data-rare-settings]')),
          in_card: !!bar.closest('.form-section, [data-group-row]')};
}"""


# ── The bar ──────────────────────────────────────────────────────────────────


def test_the_bar_is_64_px_sticky_above_the_bottom_and_stands_under_the_last_section(setup):
    """Proven red by taking `position:sticky` off `.record-bar`: at the top of a
    long form the bar is then far below the window."""
    page = _page(setup, 1440)
    top = page.evaluate(_BAR)
    print("MEASURE bar 1440 top", top)
    assert top["page"] == 1440 and top["scroll"] == 0 and top["max_scroll"] > 200, "a long form"
    assert top["bar"]["h"] == 64 and top["position"] == "sticky"
    assert top["bar"]["bottom"] == 900 - 16, "16 px above the window's bottom while scrolling"
    assert top["bar"]["x"] == top["column"]["x"] and top["bar"]["w"] == top["column"]["w"]
    assert not top["in_card"], "never in a card, never in a row"
    # Found by looking at the screenshot: both labels showed at once, because
    # `hidden` lost from the flex utility on the busy label.
    assert page.locator(f"{BAR} [data-form-save]").inner_text().strip() == "Opslaan"
    assert not page.locator(f"{BAR} [data-save-busy]").is_visible()
    assert top["remove"]["x"] < top["cancel"]["x"] < top["save"]["x"], (
        "Verwijderen left, Opslaan right"
    )
    assert top["save"]["x"] + top["save"]["w"] == top["bar"]["x"] + top["bar"]["w"] - 16

    page.evaluate("scrollTo(0, document.documentElement.scrollHeight)")
    end = page.evaluate(_BAR)
    print("MEASURE bar 1440 end", end)
    assert end["bar"]["y"] - end["rare"]["bottom"] == 24, "24 px under the last section"
    assert page.errors == []
    page.close()


def test_on_a_phone_the_bar_is_121_px_at_the_bottom_and_the_last_field_stays_reachable(setup):
    page = _page(setup, 390)
    start = page.evaluate(_BAR)
    print("MEASURE bar 390 at scroll 0", start)
    # Sticky cannot leave its form column. Until #1560 a card stood above that
    # column on a phone and the bar hung 26 px under the window before any
    # scrolling; measured again on #1560: at the bottom from the first pixel.
    assert start["bar"]["bottom"] == 844 and start["bar"]["h"] == 121
    page.evaluate("scrollTo(0, 400)")
    top = page.evaluate(_BAR)
    print("MEASURE bar 390 top", top)
    assert top["page"] == 390
    assert top["bar"]["h"] == 121 and top["bar"]["bottom"] == 844, "at the window's bottom"
    assert top["bar"]["x"] == 0 and top["bar"]["w"] == 390
    assert top["save"]["w"] == 390 - 32 and top["save"]["h"] == 44, "Opslaan full width, first line"
    assert top["save"]["y"] < top["cancel"]["y"] == top["remove"]["y"]
    assert top["remove"]["x"] == 16 and top["cancel"]["x"] + top["cancel"]["w"] == 390 - 16
    assert top["cancel"]["h"] == 44 and top["remove"]["h"] == 44

    page.evaluate("scrollTo(0, document.documentElement.scrollHeight)")
    end = page.evaluate(_BAR)
    last = page.evaluate(
        """() => { const b = document.querySelector('[data-rare-settings]').getBoundingClientRect();
                 return Math.round(b.bottom); }"""
    )
    print("MEASURE bar 390 end", end, "last section bottom", last)
    assert last <= end["bar"]["y"], "the last section ends above the bar"
    page.close()


def test_read_mode_has_no_bar_and_verwijderen_is_in_acties(setup):
    page = _page(setup, 1440, edit=False)
    assert page.locator(BAR).count() == 0
    page.click("[data-actions-trigger]")
    assert page.locator('[data-actions-menu] [role=menuitem]:has-text("Verwijderen")').count() == 1
    page.close()

    edit = _page(setup, 1440)
    edit.click("[data-actions-trigger]")
    assert (
        edit.locator('[data-actions-menu] [role=menuitem]:has-text("Verwijderen")').count() == 0
    ), "in edit mode Verwijderen lives in the bar, not also in Acties"
    assert edit.locator(f"{BAR} [data-form-delete]").count() == 1
    edit.close()


# ── A refusal ────────────────────────────────────────────────────────────────


def test_a_refusal_names_two_fields_focuses_the_first_and_keeps_everything(setup):
    """The acceptance: the name empty and a maximum of 0. Proven red by sending
    the answer without its retarget (the form is replaced and the typed
    location is gone), and by the script not marking (no reason under a field)."""
    page = _page(setup, 1440)
    page.fill("#name", "")
    page.fill("#location", "Blijft staan")
    maximum = page.locator('#aa-group-components input[name$=".max_participants"]').first
    maximum.fill("0")
    with htmx_afgerond(page):
        page.click(f"{BAR} [data-form-save]")
    banner = page.locator("#aa-fiche-message [data-save-refusal]")
    banner.wait_for()
    text = banner.inner_text()
    assert "Opslaan kan nog niet: controleer 2 velden." in text
    assert "Je andere wijzigingen zijn behouden." in text
    assert banner.locator("[data-error-for]").count() == 2

    assert page.evaluate("document.activeElement.id") == "name", (
        "the first refused field has the focus"
    )
    name_field = page.locator('[data-field="name"]')
    assert (
        name_field.locator("[data-refused-message]").inner_text()
        == "De activiteit heeft een naam nodig."
    )
    assert page.locator("#name").get_attribute("aria-invalid") == "true"
    border = page.evaluate("getComputedStyle(document.getElementById('name')).borderTopColor")
    assert border == page.evaluate(
        "(() => { const p = document.querySelector('[data-refused-message]'); return getComputedStyle(p).color; })()"
    ), "the control's line has the colour of the reason"
    assert "groter zijn dan nul" in page.locator("[data-refused-message]").nth(1).inner_text()

    assert page.locator("#location").input_value() == "Blijft staan", "every typed value is kept"
    assert maximum.input_value() == "0"
    assert page.locator("[data-form-flow]").get_attribute("data-mode") == "edit"
    assert page.locator("#toasts [data-toast]").count() == 0, "a refusal is no toast"

    # the banner's link goes to its field
    banner.locator("[data-error-for]").nth(1).click()
    assert page.evaluate("document.activeElement.name").endswith(".max_participants")

    # a second save clears the marks of the first
    page.fill("#name", NAME)
    with htmx_afgerond(page):
        page.click(f"{BAR} [data-form-save]")
    page.locator("text=controleer 1 veld").wait_for()
    assert name_field.locator("[data-refused-message]").count() == 0
    assert page.locator("#name").get_attribute("aria-invalid") is None
    assert page.errors == []
    page.close()


def test_a_refusal_arrives_without_a_view_transition(setup):
    """Refs #1589. The admin shell runs a view transition on every swap, and a
    banner that arrives is no navigation: with one the whole record cross-faded
    while the form scrolled to its first refused field (the same as measured on
    the public form page). Proven red by taking `transition:false` off the
    `HX-Reswap` of `_refusal` in `activities/admin_ui.py`."""
    page = _page(setup, 1440)
    page.fill("#name", "")
    watch_transitions(page)
    page.click(f"{BAR} [data-form-save]")
    page.locator("#aa-fiche-message [data-save-refusal]").wait_for()
    page.locator("[data-refused]").first.wait_for()
    frames = transition_frames(page)
    page.close()
    assert frames == 0, f"the record cross-fades when the banner arrives ({frames} frames)"


def test_a_removed_component_with_registrations_comes_back_with_the_reason_on_it(setup):
    """The refusal of a row the form no longer has: the row is put back, the
    reason stands on it — not a status alone."""
    page = _page(setup, 1440)
    rows = page.locator("#aa-group-components > [data-group-rows] > [data-group-row]")
    assert rows.count() == 1
    rows.first.locator("[data-row-menu-trigger]").first.click()
    rows.first.locator('[data-row-action="remove"]').first.click()
    assert rows.count() == 0
    with htmx_afgerond(page):
        page.click(f"{BAR} [data-form-save]")
    page.locator("#aa-fiche-message [data-save-refusal]").wait_for()
    assert rows.count() == 1, "the row is back"
    reason = rows.first.locator("[data-refused-message]").first.inner_text()
    assert (
        reason
        == f"Het onderdeel “{COMPONENT}” heeft één inschrijving en kan niet verwijderd worden."
    )
    assert rows.first.get_attribute("data-refused") is not None
    assert page.errors == []
    page.close()


# ── Annuleren, leaving ───────────────────────────────────────────────────────


def _dialog(page) -> dict:
    page.locator(f"{DIALOG}:visible").wait_for()
    # The dialog moves the focus on the tick after it opens: wait for the focus to
    # arrive inside it (a dialog that never takes the focus fails here), then read
    # WHICH button has it.
    page.wait_for_function(
        "document.querySelector('[data-dialog]').contains(document.activeElement)", timeout=5000
    )
    return page.evaluate(
        """() => { const d = document.querySelector('[data-dialog]');
          const ok = d.querySelector('[data-dialog-ok]'), cancel = d.querySelector('[data-dialog-cancel]');
          const bg = e => getComputedStyle(e).backgroundColor;
          return {tone: d.dataset.tone, title: d.querySelector('[data-dialog-title]').innerText, text: d.querySelector('p').innerText,
                  ok: ok.innerText, cancel: cancel.innerText, ok_bg: bg(ok), cancel_bg: bg(cancel),
                  focus: document.activeElement === cancel ? 'cancel' : document.activeElement === ok ? 'ok' : 'other'}; }"""
    )


WHITE = "rgb(255, 255, 255)"


def test_annuleren_without_changes_leaves_at_once_and_with_changes_asks(setup):
    """Proven red by swapping the two classes in the `keep` tone: the filled
    button is then the one that throws the changes away."""
    b, _s, activity_id = setup
    page = _page(setup, 1440)
    page.click(f"{BAR} [data-form-cancel]")
    page.wait_for_selector('[data-form-flow][data-mode="read"]')
    assert page.locator(DIALOG + ":visible").count() == 0
    page.close()

    page = _page(setup, 1440)
    page.fill("#location", "Niet bewaren")
    page.click(f"{BAR} [data-form-cancel]")
    d = _dialog(page)
    assert d["title"] == "Wijzigingen weggooien?"
    assert (d["cancel"], d["ok"]) == ("Verder bewerken", "Wijzigingen weggooien")
    assert d["focus"] == "cancel", "the safe button has the focus"
    assert d["cancel_bg"] != WHITE and d["ok_bg"] == WHITE, "the filled button is the safe one"
    assert page.locator(DIALOG + " button").count() == 2, "never a third 'save and leave'"

    # Esc closes the dialog and leaves the form as it is
    page.keyboard.press("Escape")
    expect(page.locator(DIALOG)).to_be_hidden()
    assert page.locator("#location").input_value() == "Niet bewaren"
    assert page.locator("[data-form-flow]").get_attribute("data-mode") == "edit"
    page.keyboard.press("Escape")
    assert page.locator("[data-form-flow]").get_attribute("data-mode") == "edit", (
        "Esc never closes the form"
    )

    page.click(f"{BAR} [data-form-cancel]")
    _dialog(page)
    page.click(f"{DIALOG} [data-dialog-ok]")
    page.wait_for_selector('[data-form-flow][data-mode="read"]')
    assert page.locator('[data-field="location"] [data-value]').inner_text() == "Parochiezaal"
    assert page.errors == []
    page.close()


def test_leaving_with_changes_asks_and_weggooien_performs_the_click(setup):
    page = _page(setup, 1440)
    page.fill("#location", "Niet bewaren")
    back = page.locator("[data-record-head] a").first
    href = back.get_attribute("href")
    back.click()
    d = _dialog(page)
    assert d["title"] == "Deze pagina verlaten?"
    assert (d["cancel"], d["ok"]) == ("Blijven", "Weggooien")
    assert d["focus"] == "cancel" and d["cancel_bg"] != WHITE and d["ok_bg"] == WHITE
    page.click(f"{DIALOG} [data-dialog-cancel]")
    assert "bewerken=1" in page.url and page.locator("#location").input_value() == "Niet bewaren"

    # a tab of the record is a way out too
    page.locator("[data-related-tabs] a").nth(1).click()
    assert _dialog(page)["title"] == "Deze pagina verlaten?"
    page.click(f"{DIALOG} [data-dialog-cancel]")

    back.click()
    _dialog(page)
    page.click(f"{DIALOG} [data-dialog-ok]")
    page.wait_for_url(lambda url: "bewerken" not in url)
    assert page.url.endswith(href) or href in page.url, (page.url, href)
    page.close()


def test_without_changes_a_link_leaves_without_a_question(setup):
    page = _page(setup, 1440)
    page.locator("[data-record-head] a").first.click()
    page.wait_for_url(lambda url: "bewerken" not in url)
    assert page.locator(DIALOG + ":visible").count() == 0
    page.close()


def test_closing_the_tab_asks_only_with_changes(setup):
    """The browser's own prompt: the page asks for it by refusing `beforeunload`,
    and only while something changed."""
    refuses = """() => { const e = new Event('beforeunload', {cancelable: true});
                       window.dispatchEvent(e); return e.defaultPrevented; }"""
    page = _page(setup, 1440)
    assert page.evaluate(refuses) is False, "nothing changed, nothing asked"
    page.fill("#location", "Niet bewaren")
    assert page.evaluate(refuses) is True
    page.fill("#location", "Parochiezaal")
    assert page.evaluate(refuses) is False, "typed back to what it was is no change"
    page.close()


# ── Saved, failed, the keyboard ──────────────────────────────────────────────


def test_ctrl_s_saves_and_the_toast_says_so_in_read_mode(setup):
    """#748: the toast after success. Proven red by leaving the listener out:
    the browser's own save-page takes the keys and nothing is written."""
    page = _page(setup, 1440)
    page.fill("#location", "Dorpshuis")
    page.keyboard.press("Control+s")
    page.wait_for_selector('[data-form-flow][data-mode="read"]')
    toast = page.locator('#toasts [data-toast="success"]')
    toast.wait_for()
    assert "Opgeslagen" in toast.inner_text()
    box = toast.bounding_box()
    print("MEASURE toast 1440", box)
    assert box["y"] >= 64 and box["x"] + box["width"] == 1440 - 16, "top right, under the top bar"
    assert page.locator('[data-field="location"] [data-value]').inner_text() == "Dorpshuis"
    assert page.errors == []
    # back to what the other tests expect
    page.goto(page.url.split("?")[0] + "?bewerken=1")
    pagina_klaar(page)
    page.fill("#location", "Parochiezaal")
    page.click(f"{BAR} [data-form-save]")
    page.wait_for_selector('[data-form-flow][data-mode="read"]')
    page.close()


def test_a_failed_save_says_so_in_the_form_and_not_in_a_toast(setup):
    """#649, for a record form: the 403 of a stale token. Three attempts give
    one message. Proven red by not handing the reason to the form: the generic
    toast appears instead."""
    page = _page(setup, 1440)
    page.fill("#location", "Blijft staan")
    page.evaluate(
        "document.body.setAttribute('hx-headers', JSON.stringify({'X-CSRF-Token': 'verlopen-token'}))"
    )
    for _attempt in range(3):
        with htmx_afgerond(page):
            page.click(f"{BAR} [data-form-save]")
    failure = page.locator("#aa-fiche-message [data-save-failure]")
    assert failure.count() == 1
    text = failure.inner_text()
    assert "Opslaan is niet gelukt." in text and "Herlaad de pagina" in text
    assert page.locator("#toasts [data-fout]").count() == 0, "no toast for a failed save"
    assert page.locator("#location").input_value() == "Blijft staan", "nothing lost"
    save = page.locator(f"{BAR} [data-form-save]")
    assert save.is_enabled() and save.locator("[data-save-idle]").is_visible(), (
        "the button is Opslaan again"
    )
    assert page.errors == []
    page.close()


def test_while_saving_the_button_says_so_and_the_form_is_inert(setup):
    page = _page(setup, 1440)
    page.fill("#location", "Parochiezaal ")
    # The save is held until the state was read: no clock involved.
    held = []
    page.route(
        "**/admin/activiteiten/*",
        lambda route: held.append(route) if route.request.method == "POST" else route.continue_(),
    )
    page.click(f"{BAR} [data-form-save]")
    page.wait_for_function(
        "document.querySelector('[data-action-bar]').hasAttribute('data-saving')"
    )
    busy = page.evaluate(
        """() => { const bar = document.querySelector('[data-action-bar]'), save = bar.querySelector('[data-form-save]');
          return {label: save.innerText.trim(), disabled: save.disabled, inert: document.getElementById('aa-act-form').inert,
                  spinner: !!save.querySelector('.record-spinner') && save.querySelector('[data-save-busy]').checkVisibility()}; }"""
    )
    assert busy == {"label": "Opslaan…", "disabled": True, "inert": True, "spinner": True}
    assert len(held) == 1
    held[0].continue_()
    page.wait_for_selector('[data-form-flow][data-mode="read"]')
    page.close()


# ── Verwijderen and the state commands ───────────────────────────────────────


def test_verwijderen_on_an_activity_with_registrations_says_why_and_asks_nothing(setup):
    """NEW (Koen, 4 October 2026): the refusal comes before any confirmation. In
    the bar a notice with one button; in Acties the item itself says it."""
    page = _page(setup, 1440)
    posts = []
    page.on("request", lambda req: posts.append(req.url) if req.method == "POST" else None)
    page.click(f"{BAR} [data-form-delete]")
    d = _dialog(page)
    assert d["tone"] == "notice"
    assert d["title"] == f"“{NAME}” kan niet verwijderd worden"
    assert "heeft 1 inschrijving" in d["text"] and "Activiteit annuleren" in d["text"]
    assert d["cancel"] == "Sluiten" and d["focus"] == "cancel"
    assert not page.locator(f"{DIALOG} [data-dialog-ok]").is_visible(), (
        "one button: nothing to confirm"
    )
    page.click(f"{DIALOG} [data-dialog-cancel]")
    expect(page.locator(DIALOG)).to_be_hidden()
    assert posts == [] and "bewerken=1" in page.url
    page.close()

    read = _page(setup, 1440, edit=False)
    read.click("[data-actions-trigger]")
    refused = read.locator("[data-actions-menu] [data-menu-refused]")
    assert "heeft 1 inschrijving en kan niet verwijderd worden" in refused.inner_text()
    assert read.locator('[data-actions-menu] [hx-post$="/verwijderen"]').count() == 0
    read.close()


def test_the_delete_dialog_names_the_record_with_a_red_filled_button(setup):
    """The delete tone, on the kit's page (the seeded activity has a registration
    and is refused before it comes to this dialog)."""
    b, session, _id = setup
    page = b.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
    login_met_sessie(page, session)
    page.goto("/admin/design-system")
    pagina_klaar(page)
    page.click('[data-kit-dialog][data-tone="delete"] button')
    d = _dialog(page)
    assert d["tone"] == "delete" and d["title"].endswith("verwijderen?")
    assert (d["cancel"], d["ok"]) == ("Annuleren", "Definitief verwijderen")
    assert d["focus"] == "cancel"
    red = page.evaluate(
        """() => { const c = getComputedStyle(document.querySelector('[data-dialog-ok]')).backgroundColor.match(/\\d+/g).map(Number);
                 return c[0] > 120 && c[0] > 2 * c[1] && c[0] > 2 * c[2]; }"""
    )
    assert red, "Definitief verwijderen is filled red"
    page.keyboard.press("Escape")
    expect(page.locator(DIALOG)).to_be_hidden()
    page.close()


def test_a_state_command_asks_with_its_consequence_then_says_it_happened(setup):
    page = _page(setup, 1440, edit=False)
    badge = page.locator("[data-record-head] [data-badges]")
    before = badge.inner_text()
    page.click("[data-actions-trigger]")
    item = page.locator("[data-actions-menu] [role=menuitem]").filter(has_text="concept")
    if item.count() == 0:
        item = page.locator("[data-actions-menu] [role=menuitem]").filter(has_text="Publiceren")
    label = item.first.inner_text().strip()
    item.first.click()
    page.locator(f"{DIALOG}:visible").wait_for()
    assert page.locator(DIALOG).get_attribute("data-tone") == "confirm", "the lighter dialog"
    assert page.locator(f"{DIALOG} [data-dialog-ok]").inner_text() == label
    assert len(page.locator(f"{DIALOG} p").inner_text()) > 30, "it names its consequence"
    with page.expect_navigation():
        page.click(f"{DIALOG} [data-dialog-ok]")
    pagina_klaar(page)
    toast = page.locator('#toasts [data-toast="success"]')
    toast.wait_for()
    assert toast.inner_text().strip().startswith(("Teruggezet naar concept", "Gepubliceerd"))
    assert badge.inner_text() != before, "the badge changed"
    # and back, so the other tests find the activity as it was
    page.click("[data-actions-trigger]")
    page.locator("[data-actions-menu] [role=menuitem]").filter(has_text="ublice").first.click()
    with page.expect_navigation():
        page.click(f"{DIALOG} [data-dialog-ok]")
    page.close()

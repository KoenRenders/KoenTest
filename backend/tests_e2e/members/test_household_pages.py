"""E2E: Word lid, Mijn gezin and the renewal on the public form page (CR-11 pilot B,
#1590; design-system-end-state §2.6, §3.3).

Through a browser, because what this slice promises lives there: rows that fold
and open, a tag that moves, a button whose words follow a choice, one bar that
stays in reach down a long page, a refusal that opens the folded row it is about
— and ONE request for a household with its persons, addresses and address. The
stored result is read back through a session of our own, so a flush cannot pass
for a commit.

Each test signs a household of its own up through the page and removes it again:
the e2e tests share their seed, and a leftover household or transfer shifts
others (#1241).

Broken on purpose (5 October 2026), one exact replacement each, each red:
- every person row rendered open → the fold assertions of Mijn gezin and of the
  refused save;
- the tag no longer toggled by `refreshOne` → "the tag stands on two rows";
- the page asking another address for the relation → the added person stays a child;
- `record-form.js` no longer opening the `<details>` of a refused field → the
  refused field is not visible, on Word lid and on Mijn gezin;
- the bar without `save_label_attrs` → the button keeps "Word lid en betaal" (and
  "Betalen" on the renewal — "Vernieuwen en betalen" until #1737);
- the toast left out of the save's answer → no "Opgeslagen ✓";
- the save's answer rendered in edit mode → the page does not return to reading;
- Mijn gezin always in edit mode → the read-mode, cancel and renewal-link tests.
"""

import os
import sys
import uuid
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (  # noqa: E402
    BASE,
    HOUSEHOLD_ROWS,
    fill_person,
    login_met_sessie,
    pagina_klaar,
)

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1440, "height": 900}
PERSONS = HOUSEHOLD_ROWS
#: The main member's section (#1632): no row of the group.
HEAD = "#hoofdlid"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _open(browser, path: str, viewport=None, session: str | None = None):
    page = browser.new_page(base_url=BASE, viewport=viewport or DESKTOP)
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.posts = []
    page.on("request", lambda r: page.posts.append(r.url) if r.method == "POST" else None)
    if session:
        login_met_sessie(page, session)
    page.goto(path)
    pagina_klaar(page)
    return page


def _db():
    import app.main  # noqa: F401  the whole app, so the domain facades import in order
    from app.database import SessionLocal

    return SessionLocal()


def _household(email: str) -> dict | None:
    """What is stored for the household of the person owning `email`, read in a
    session of our own: persons with their e-mail rows, and the address."""
    from app.domains.mdm.api import ContactDetail, MemberPerson, Person

    db = _db()
    try:
        person_id = db.query(ContactDetail.person_id).filter(ContactDetail.value == email).scalar()
        if person_id is None:
            return None
        member_id = (
            db.query(MemberPerson.member_id).filter(MemberPerson.person_id == person_id).scalar()
        )
        links = (
            db.query(MemberPerson)
            .filter(MemberPerson.member_id == member_id, MemberPerson.deleted_at.is_(None))
            .all()
        )
        persons = {}
        address = None
        for link in links:
            p = db.get(Person, link.person_id)
            mails = {
                c.value: bool(c.is_primary)
                for c in p.contact_details
                if c.contact_type_code == "EMAIL"
            }
            persons[p.first_name] = {
                "last_name": p.last_name,
                "relation": link.relation_type.value,
                "emails": mails,
                "mobile": next(
                    (c.value for c in p.contact_details if c.contact_type_code == "MOBILE"), None
                ),
            }
            if p.address is not None:
                address = (p.address.street, p.address.house_number, p.address.bus_number)
        return {"member_id": member_id, "persons": persons, "address": address}
    finally:
        db.close()


def _history(member_id: int) -> list[str]:
    """Every action the history tables hold for this household's persons, their
    e-mail rows, their address and their links — the "Wijzigingen" of the board."""
    from app.domains.mdm.models import (
        AddressHistory,
        ContactDetailHistory,
        MemberPerson,
        MemberPersonHistory,
        PersonHistory,
    )

    db = _db()
    try:
        ids = [
            pid
            for (pid,) in db.query(MemberPerson.person_id)
            .execution_options(include_deleted=True)
            .filter(MemberPerson.member_id == member_id)
        ]
        found: list[str] = []
        for model in (PersonHistory, ContactDetailHistory, AddressHistory, MemberPersonHistory):
            found += [r.action for r in db.query(model).filter(model.person_id.in_(ids))]
        return sorted(found)
    finally:
        db.close()


def _remove(email: str) -> None:
    from app.domains.mdm.api import delete_household

    stored = _household(email)
    if stored is None:
        return
    db = _db()
    try:
        delete_household(
            db, stored["member_id"], admin=SimpleNamespace(email="e2e-1590@example.com")
        )
    finally:
        db.close()


def _sign_up(
    browser, tag: str, *, partner: bool = True, partner_email: str = "", second_email: str = ""
) -> str:
    """A household of our own, paid by transfer; its main address.

    Made by the sign-up's own reader and service in this process, not through the
    page: `POST /lid-worden` is rate-limited per visitor, and four sign-ups from
    this file left the tests after it with "Je gaat sneller dan de server
    verwerkt" (measured: the online payment chain got a 429). The page itself is
    walked once, by the first test.
    """
    from fastapi import BackgroundTasks
    from starlette.datastructures import FormData

    from app.domains.membership.api import register_family
    from app.domains.membership.signup_form import signup_from_form

    email = f"e2e.gezin.{tag}@example.com"
    fields = [
        ("h_order", "n0"),
        ("h.n0.first_name", "Hoofd"),
        ("h.n0.last_name", f"Gezin {tag}"),
        ("h.n0.date_of_birth", "1980-01-01"),
        ("h.n0.gender_code", "M"),
        ("h.n0.mobile", "0470000000"),
        ("e_order.n0", "n0e"),
        ("e.n0e.value", email),
        ("e_primary.n0", "n0e"),
        ("address.street", "Teststraat"),
        ("address.house_number", "1"),
        ("address.postal_code", "2400"),
        ("payment_method", "transfer"),
    ]
    if partner:
        fields += [
            ("h_order", "n1"),
            ("h.n1.first_name", "Partner"),
            ("h.n1.last_name", f"Gezin {tag}"),
            ("h.n1.date_of_birth", "1981-02-02"),
            ("h.n1.gender_code", "F"),
        ]
    if second_email:
        fields += [("e_order.n0", "n0f"), ("e.n0f.value", second_email)]
    if partner and partner_email:
        if True:
            fields += [
                ("e_order.n1", "n1e"),
                ("e.n1e.value", partner_email),
                ("e_primary.n1", "n1e"),
            ]
    data, errors = signup_from_form(FormData(fields))
    assert data is not None, errors
    db = _db()
    try:
        register_family(db, data, BackgroundTasks())
    finally:
        db.close()
    assert _household(email) is not None, "the household was not stored"
    return email


def _session(email: str) -> str:
    from app.domains.auth.api import make_session_value

    return make_session_value(email)


_FOLDS = """() => [...document.querySelectorAll('#gezinsleden > [data-group-rows] > [data-group-row]')]
  .map(r => r.querySelector('details[data-row-fold]').open)"""
_TAGS = """(row) => [...row.querySelectorAll('[data-row-one-tag]')].filter(t => t.checkVisibility()).length"""
_BAR = """() => { const b = document.querySelector('[data-action-bar]').getBoundingClientRect();
  return {top: Math.round(b.top), bottom: Math.round(b.bottom), window: innerHeight,
          page: document.documentElement.scrollHeight, width: document.documentElement.scrollWidth}; }"""


def test_word_lid_on_a_phone_from_the_first_field_to_the_stored_household(browser):
    tag = uuid.uuid4().hex[:8]
    first, second = f"e2e.een.{tag}@example.com", f"e2e.twee.{tag}@example.com"
    page = _open(browser, "/lid-worden", PHONE)
    try:
        # ── As it opens: the main member's section, no row yet (#1632); a
        # postal code that is a select ──
        expect(page.locator(HEAD)).to_be_visible()
        assert page.evaluate(_FOLDS) == []
        assert page.locator("#address-postal_code").evaluate("e => e.tagName") == "SELECT"
        bar = page.evaluate(_BAR)
        assert bar["width"] == 390, f"the page scrolls sideways: {bar}"
        assert bar["bottom"] == bar["window"], f"the bar does not stand at the bottom: {bar}"
        assert page.locator("text=Verplicht veld").count() == 0
        assert page.locator("[data-member-nudge]").count() == 0, "Word lid carries no nudge"

        # ── A person added: open, focused, and a partner by the one rule ──
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        rows = page.locator(PERSONS)
        expect(rows).to_have_count(1)
        partner = rows.nth(0)
        assert page.evaluate("document.activeElement.name").endswith(".first_name")
        assert partner.locator('input[name$=".first_name"]').evaluate(
            "e => e === document.activeElement"
        )
        expect(partner.locator('select[name$=".relation_type"]')).to_have_value("PARTNER")
        expect(partner.locator("[data-row-title-prefix]")).to_have_text("Partner")
        # the next one is a child: the rule is asked, not copied
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        child = rows.nth(1)
        expect(child.locator('select[name$=".relation_type"]')).not_to_have_value("PARTNER")
        expect(child.locator('select[name$=".relation_type"]')).not_to_have_value("")
        # the title follows the names
        fill_person(partner, "Marie", f"Rijen {tag}", gender="F")
        expect(partner.locator("[data-row-title]")).to_have_text(f"Marie Rijen {tag}")

        # ── A row that was never saved goes without a question ──
        # the person's own menu — the e-mail field they open with has one too (#1641)
        child.locator(".group-fold-menu [data-row-menu-trigger]").click()
        child.locator(".group-fold-menu").get_by_role("menuitem", name="Verwijderen").click()
        expect(rows).to_have_count(1)
        assert page.locator("[data-dialog]:visible").count() == 0, (
            "removing an unsaved row asked something"
        )

        # ── The main member's addresses: one tag, and it moves ──
        head = page.locator(HEAD)
        fill_person(head, "E2E", f"Rijen {tag}")
        head.locator('input[name$=".mobile"]').fill("0470000000")
        head.locator('input[type="email"]').first.fill(first)
        assert head.evaluate(_TAGS) == 1
        # #1603: the main address may be removed like any other (its menu holds
        # "Verwijderen"), but it is not offered to become what it already is.
        head.locator("[data-row-menu-trigger]:visible").click()
        expect(head.get_by_role("menuitem", name="Verwijderen")).to_be_visible()
        expect(head.get_by_role("menuitem", name="Maak hoofdadres")).to_have_count(0)
        page.keyboard.press("Escape")
        head.locator("[data-repeating-group] [data-group-add]").click()
        mails = head.locator('input[type="email"]')
        expect(mails).to_have_count(2)
        mails.nth(1).fill(second)
        assert head.evaluate(_TAGS) == 1, "the tag stands on two rows"
        head.locator("[data-row-menu-trigger]:visible").nth(1).click()
        head.get_by_role("menuitem", name="Maak hoofdadres").click()
        assert head.evaluate(_TAGS) == 1, "the tag stands on two rows after the choice"
        tagged = head.evaluate(
            """row => [...row.querySelectorAll('[data-group-row]')]
                 .find(r => r.querySelector('[data-row-one-tag]').checkVisibility())
                 .querySelector('input[type=email]').value"""
        )
        assert tagged == second

        # ── The button names the next step ──
        save = page.locator("[data-form-save]")
        expect(save.locator("[data-save-idle]")).to_have_text("Word lid en betaal")
        page.check('input[name="payment_method"][value="transfer"]')
        expect(save.locator("[data-save-idle]")).to_have_text("Word lid")

        # ── A refusal: the banner names the field in the folded row, opens it ──
        partner.locator('input[name$=".first_name"]').fill("")
        partner.locator("summary").click()
        assert page.evaluate(_FOLDS) == [False]
        page.fill("#address-street", "Teststraat")
        page.fill("#address-house_number", "1")
        page.posts.clear()
        save.click()
        banner = page.locator("[data-save-refusal]")
        expect(banner).to_be_visible()
        expect(banner).to_contain_text("Verzenden kan nog niet: controleer 2 velden.")
        refused = partner.locator('input[name$=".first_name"]')
        expect(refused).to_be_visible()
        assert page.evaluate(_FOLDS) == [True], "the refused row stayed folded"
        expect(refused).to_be_focused()
        expect(refused).to_have_attribute("aria-invalid", "true")
        expect(page.locator('[data-field="address.postal_code"]')).to_have_attribute(
            "data-refused", ""
        )
        # everything typed is still there
        expect(head.locator('input[name$=".first_name"]')).to_have_value("E2E")
        expect(mails.nth(1)).to_have_value(second)
        assert _household(first) is None, "a refused sign-up stored something"

        # ── The bar stays in reach down the page ──
        # (it sticks to the bottom while the form runs on, and lands where the form
        # ends — so it is in view at every position down to there)
        form_end = page.evaluate(
            "Math.round(document.querySelector('#lidgeld').getBoundingClientRect().bottom + scrollY)"
        )
        for y in (0, form_end // 4, form_end // 2):
            page.evaluate(f"scrollTo(0, {y})")
            bar = page.evaluate(_BAR)
            assert bar["bottom"] == bar["window"], f"at {y}: the bar left the bottom: {bar}"
        page.evaluate(f"scrollTo(0, {form_end})")
        bar = page.evaluate(_BAR)
        assert 0 <= bar["top"] and bar["bottom"] <= bar["window"], f"the bar is out of view: {bar}"

        # ── Sent: one request, the confirmation, and what is stored ──
        refused.fill("Marie")
        page.select_option("#address-postal_code", index=1)
        page.posts.clear()
        save.click()
        expect(page.get_by_role("heading", name="Je aanvraag is ontvangen")).to_be_visible()
        expect(page.locator("[data-payment-pending]")).to_be_visible()
        assert [u for u in page.posts if u.endswith("/lid-worden")] == [f"{BASE}/lid-worden"]
        assert page.errors == []
        stored = _household(first)
        assert stored is not None
        assert stored["persons"]["E2E"]["emails"] == {first: False, second: True}
        assert stored["persons"]["E2E"]["relation"] == "HOOFDLID"
        assert stored["persons"]["Marie"]["relation"] == "PARTNER"
        assert set(stored["persons"]) == {"E2E", "Marie"}
        assert stored["address"] == ("Teststraat", "1", None)
    finally:
        page.close()
        _remove(first)


def test_mijn_gezin_reads_first_and_saves_everything_with_one_opslaan(browser):
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag)
    new_mail = f"e2e.nieuw.{tag}@example.com"
    page = _open(browser, "/leden/gezin", session=_session(email))
    try:
        # ── Read mode: no control, one Bewerken, the same sections ──
        flow = page.locator("[data-form-flow]")
        expect(flow).to_have_attribute("data-mode", "read")
        assert (
            page.locator("main input:not([type=hidden]), main select, main textarea").count() == 0
        )
        assert page.locator("[data-action-bar]").count() == 0
        expect(page.get_by_role("link", name="Bewerken")).to_have_count(1)
        assert page.evaluate(_FOLDS) == [False]
        expect(page.locator('[data-field$=".phone"] [data-value]').first).to_have_text("—")
        before = _history(_household(email)["member_id"])

        # ── Edit mode: one badge, one bar; change four things ──
        page.get_by_role("link", name="Bewerken").click()
        pagina_klaar(page)
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "edit")
        expect(page.locator("[data-page-badge]")).to_have_text("Bewerken")
        expect(page.locator("[data-action-bar]")).to_have_count(1)
        expect(page.locator("[data-form-save] [data-save-idle]")).to_have_text("Opslaan")
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        rows = page.locator(PERSONS)
        head = page.locator(HEAD)
        head.locator('input[name$=".first_name"]').fill("Theo")
        head.locator("[data-repeating-group] [data-group-add]").click()
        head.locator('input[type="email"]').nth(1).fill(new_mail)
        page.fill("#address-street", "Nieuwstraat")
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        fill_person(rows.nth(1), "Kind", f"Gezin {tag}", born="2015-05-05", gender="F")

        page.posts.clear()
        page.locator("[data-form-save]").click()

        # ── One request; read mode again; the toast; the values ──
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        expect(page.locator("#toasts")).to_contain_text("Opgeslagen ✓")
        assert page.posts == [f"{BASE}/leden/gezin"], page.posts
        assert page.url == f"{BASE}/leden/gezin"
        expect(page.locator(PERSONS)).to_have_count(2)
        expect(page.locator('[data-field$=".first_name"] [data-value]').first).to_have_text("Theo")
        assert page.errors == []

        # ── Stored, read in a session of our own; one history row per thing ──
        stored = _household(email)
        assert set(stored["persons"]) == {"Theo", "Partner", "Kind"}
        assert stored["persons"]["Theo"]["emails"] == {email: True, new_mail: False}
        assert stored["address"][0] == "Nieuwstraat"
        written = list(_history(stored["member_id"]))
        for action in before:
            written.remove(action)
        assert written == sorted(
            [
                "person_updated",
                "email_added",
                "address_updated",
                "person_created",
                "person_added_to_family",
            ]
        ), written
    finally:
        page.close()
        _remove(email)


def test_a_refused_save_opens_the_folded_row_and_keeps_the_rest(browser):
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag)
    page = _open(browser, "/leden/gezin?bewerken=1", session=_session(email))
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        rows = page.locator(PERSONS)
        assert page.evaluate(_FOLDS) == [False]
        # the partner's row is folded; its first name is emptied without opening it
        rows.nth(0).locator('input[name$=".first_name"]').evaluate(
            "e => { e.value = ''; e.dispatchEvent(new Event('input', {bubbles: true})); }"
        )
        page.fill("#address-street", "Blijfstraat")
        page.locator("[data-form-save]").click()

        banner = page.locator("[data-save-refusal]")
        expect(banner).to_contain_text("Opslaan kan nog niet: controleer 1 veld.")
        refused = rows.nth(0).locator('input[name$=".first_name"]')
        expect(refused).to_be_visible()
        expect(refused).to_be_focused()
        assert page.evaluate(_FOLDS) == [True]
        expect(page.locator("#address-street")).to_have_value("Blijfstraat")
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "edit")
        stored = _household(email)
        assert stored["address"][0] == "Teststraat", "a refused save wrote the address"
        assert set(stored["persons"]) == {"Hoofd", "Partner"}
    finally:
        page.close()
        _remove(email)


def test_annuleren_and_leaving_ask_before_changes_are_lost(browser):
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag, partner=False)
    page = _open(browser, "/leden/gezin?bewerken=1", session=_session(email))
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        # unchanged: Annuleren just leaves
        page.locator("[data-form-cancel]").click()
        pagina_klaar(page)
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")

        page.goto("/leden/gezin?bewerken=1")
        pagina_klaar(page)
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        page.fill("#address-street", "Weggooistraat")
        page.locator("[data-form-cancel]").click()
        dialog = page.locator("[data-dialog]")
        expect(dialog.locator("[data-dialog-title]")).to_have_text("Wijzigingen weggooien?")
        dialog.locator("[data-dialog-ok]").click()
        pagina_klaar(page)
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        expect(page.locator('[data-field="address.street"] [data-value]')).to_have_text(
            "Teststraat"
        )
        assert _household(email)["address"][0] == "Teststraat"
    finally:
        page.close()
        _remove(email)


def test_the_renewal_is_its_own_page_and_its_button_follows_the_choice(browser):
    from seed_e2e import MARKER_EMAIL_VERLOPEN

    for viewport in (PHONE, DESKTOP):
        page = _open(
            browser, "/leden/gezin/vernieuwen", viewport, session=_session(MARKER_EMAIL_VERLOPEN)
        )
        try:
            # #1737: the page is named for what everyone does on it.
            expect(page.get_by_role("heading", name="Lidmaatschap betalen")).to_be_visible()
            expect(page.locator("[data-renewal-status]")).to_contain_text(
                "geen geldig lidmaatschap"
            )
            terms = page.locator("[data-membership-terms]")
            expect(terms).to_contain_text("€")
            expect(terms).to_contain_text("Geldig tot en met")
            save = page.locator("[data-form-save]")
            expect(save.locator("[data-save-idle]")).to_have_text("Betalen")
            page.check('input[name="payment_method"][value="transfer"]')
            # #1747: with a transfer nothing is paid at that moment.
            expect(save.locator("[data-save-idle]")).to_have_text("Lidmaatschap aanvragen")
            expect(page.locator("[data-household-summary]")).to_contain_text("Hoofdlid")
            expect(
                page.locator("[data-household-summary]").get_by_role("link", name="Naar Mijn gezin")
            ).to_be_visible()
            width = page.evaluate("document.documentElement.scrollWidth")
            assert width == viewport["width"]
            assert page.errors == []
        finally:
            page.close()


def test_mijn_gezin_points_to_the_renewal_and_carries_no_form_for_it(browser):
    from seed_e2e import MARKER_EMAIL_VERLOPEN

    page = _open(browser, "/leden/gezin", session=_session(MARKER_EMAIL_VERLOPEN))
    try:
        status = page.locator("[data-membership-status]")
        expect(status).to_contain_text("geen geldig lidmaatschap")
        assert page.locator('input[name="payment_method"]').count() == 0
        status.get_by_role("link", name="Lidmaatschap vernieuwen").click()
        pagina_klaar(page)
        assert page.url == f"{BASE}/leden/gezin/vernieuwen"
    finally:
        page.close()


# ── #1607: the action bar against the window's bottom, on a public page too ──

_STUCK = """() => { const bar = document.querySelector('[data-action-bar]'), b = bar.getBoundingClientRect();
  const bell = document.querySelector('[data-raakje-bell]');
  const column = document.querySelector('[data-public-form-page]').getBoundingClientRect();
  return {bottom: Math.round(b.bottom), top: Math.round(b.top), x: Math.round(b.left), w: Math.round(b.width),
          window: document.documentElement.clientHeight, shadow: getComputedStyle(bar).boxShadow,
          column: [Math.round(column.left), Math.round(column.width)],
          bell: bell && bell.checkVisibility() ? Math.round(bell.getBoundingClientRect().bottom) : null}; }"""
_HAS_SHADOW = "getComputedStyle(document.querySelector('[data-action-bar]')).boxShadow !== 'none'"


@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["1440", "390"])
def test_the_bar_of_a_public_form_stands_against_the_windows_bottom(browser, viewport):
    """#1607 (Koen, 5 October 2026; end state §3.6): the same macro serves the
    public form pages, so Word lid — the longest of them — shows the same bar:
    against the window's bottom with its shadow upward while the form runs on,
    as wide as the form column on a desktop, and in the flow without a shadow at
    the form's end. On a phone the bell stays 16 px above it.

    Red on master at 1 440 px: the bar's bottom stood 16 px above the window's
    (884 against 900), and it cast no shadow at any width.
    """
    page = _open(browser, "/lid-worden", viewport)
    try:
        page.wait_for_function(_HAS_SHADOW)
        top = page.evaluate(_STUCK)
        assert top["bottom"] == top["window"] == viewport["height"], top
        if viewport is DESKTOP:
            assert (top["x"], top["w"]) == tuple(top["column"]), "not as wide as the form column"
        else:
            assert (top["x"], top["w"]) == (0, 390)
            if top["bell"] is not None:
                assert top["bell"] == top["top"] - 16, "the bell does not sit 16 px above the bar"
        # scrolled, it still stands there: nothing of the form shows under it
        page.evaluate("scrollTo(0, 400)")
        page.wait_for_function(_HAS_SHADOW)
        assert page.evaluate(_STUCK)["bottom"] == viewport["height"]
        # at the form's end it is in the flow, and a plain row again
        # (by the last section: a sticky bar is "in view" wherever the page stands)
        page.evaluate(
            "scrollTo(0, document.querySelector('#lidgeld').getBoundingClientRect().bottom"
            " + scrollY - innerHeight / 2)"
        )
        page.wait_for_function(f"!({_HAS_SHADOW})")
        end = page.evaluate(_STUCK)
        assert end["bottom"] < end["window"], end
        assert page.errors == []
    finally:
        page.close()


# ── #1603: Koen's rules of 5 October 2026 ────────────────────────────────────

_RELATION = 'select[name$=".relation_type"]'


def test_word_lid_on_a_phone_the_default_and_the_choice_of_partner_or_child(browser):
    """Rule 2 on Word lid: a person added starts as the partner while there is
    none, the member may choose child, and the default of the NEXT person counts
    that choice — the page asks the one rule each time. Never main member: the
    list does not offer it."""
    page = _open(browser, "/lid-worden", PHONE)
    try:
        rows = page.locator(PERSONS)
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        first = rows.nth(0)
        expect(first.locator(_RELATION)).to_have_value("PARTNER")
        assert first.locator(f"{_RELATION} option").evaluate_all("o => o.map(x => x.value)") == [
            "PARTNER",
            "KIND",
        ]
        first.locator(_RELATION).select_option("KIND")
        expect(first.locator("[data-row-title-prefix]")).not_to_have_text("Partner")
        # nobody is the partner now, so the next person is
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        expect(rows.nth(1).locator(_RELATION)).to_have_value("PARTNER")
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        expect(rows.nth(2).locator(_RELATION)).to_have_value("KIND")
        assert page.evaluate("document.documentElement.scrollWidth") == 390
        assert page.errors == []
    finally:
        page.close()


def test_mijn_gezin_on_a_phone_the_default_and_the_choice_of_partner_or_child(browser):
    """Rule 2 on Mijn gezin, the same control and the same rule: in a household of
    one the person added is the partner; the member chooses child instead; the
    next is the partner again; and what was chosen is what is stored. A person
    who is already there has no such list."""
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag, partner=False)
    page = _open(browser, "/leden/gezin?bewerken=1", PHONE, session=_session(email))
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        rows = page.locator(PERSONS)
        assert page.locator(HEAD).locator(_RELATION).count() == 0, "the main member can be re-typed"
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        child = rows.nth(0)
        expect(child.locator(_RELATION)).to_have_value("PARTNER")
        expect(child.locator("[data-row-title-prefix]")).to_have_text("Partner")
        child.locator(_RELATION).select_option("KIND")
        expect(child.locator("[data-row-title-prefix]")).not_to_have_text("Partner")
        fill_person(child, "Kind", f"Gezin {tag}", born="2014-04-04", gender="F")
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        partner = rows.nth(1)
        expect(partner.locator(_RELATION)).to_have_value("PARTNER")
        fill_person(partner, "Lief", f"Gezin {tag}", gender="F")
        assert page.evaluate("document.documentElement.scrollWidth") == 390

        page.locator("[data-form-save]").click()
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        stored = _household(email)["persons"]
        assert {name: p["relation"] for name, p in stored.items()} == {
            "Hoofd": "HOOFDLID",
            "Kind": "KIND",
            "Lief": "PARTNER",
        }
        # saved, the two are persons of the household: no list any more
        page.goto("/leden/gezin?bewerken=1")
        pagina_klaar(page)
        assert page.locator(f"{PERSONS} {_RELATION}").count() == 0
        assert page.errors == []
    finally:
        page.close()
        _remove(email)


def _drop_address(email: str) -> None:
    """Take the household's address away, as a household made by the board or an
    import can be without one."""
    from app.domains.mdm.api import Address, ContactDetail

    db = _db()
    try:
        person_id = db.query(ContactDetail.person_id).filter(ContactDetail.value == email).scalar()
        db.query(Address).filter(Address.person_id == person_id).delete()
        db.commit()
    finally:
        db.close()


def test_a_household_without_an_address_can_give_itself_one(browser):
    """Rule 4: the section is there with empty fields and asks nothing; one field
    filled asks the three, at the field that is missing; the whole address is
    created with the page's one save."""
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag, partner=False)
    _drop_address(email)
    assert _household(email)["address"] is None
    page = _open(browser, "/leden/gezin", session=_session(email))
    try:
        # read mode: the section stands, every value a dash
        section = page.locator("#gezin-adres")
        expect(section).to_be_visible()
        assert section.locator("[data-value]").all_inner_texts() == ["—", "—", "—", "—"]

        page.goto("/leden/gezin?bewerken=1")
        pagina_klaar(page)
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        section = page.locator("#gezin-adres")
        expect(section).to_contain_text("Je gezin heeft nog geen adres.")
        assert section.locator("[required]").count() == 0, "an empty address section asks a field"
        # untouched, the save goes through and there is still no address
        page.locator("[data-form-save]").click()
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        assert _household(email)["address"] is None

        page.goto("/leden/gezin?bewerken=1")
        pagina_klaar(page)
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        page.fill("#address-street", "Kerkstraat")
        page.locator("[data-form-save]").click()
        expect(page.locator("[data-save-refusal]")).to_contain_text(
            "Een adres heeft een straat, een huisnummer en een postcode nodig."
        )
        expect(page.locator("#address-house_number")).to_be_focused()
        expect(page.locator("#address-street")).to_have_value("Kerkstraat")
        assert _household(email)["address"] is None

        page.fill("#address-house_number", "5")
        page.select_option("#address-postal_code", index=1)
        page.locator("[data-form-save]").click()
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        expect(page.locator('[data-field="address.street"] [data-value]')).to_have_text(
            "Kerkstraat"
        )
        assert _household(email)["address"] == ("Kerkstraat", "5", None)
        assert page.errors == []
    finally:
        page.close()
        _remove(email)


def test_the_main_address_may_go_and_nothing_takes_its_place(browser):
    """Rule 3 (Koen, 27 September 2026, confirmed): the main e-mail address is
    removed like any other, the tag does not jump to the address that is left,
    and what is stored has no main address."""
    tag = uuid.uuid4().hex[:8]
    other = f"e2e.blijft.{tag}@example.com"
    email = _sign_up(browser, tag, partner=False, second_email=other)
    page = _open(browser, "/leden/gezin?bewerken=1", session=_session(email))
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        head = page.locator(HEAD)
        expect(head.locator('input[type="email"]')).to_have_count(2)
        assert head.evaluate(_TAGS) == 1
        head.locator("[data-row-menu-trigger]:visible").first.click()
        head.get_by_role("menuitem", name="Verwijderen").click()
        expect(head.locator('input[type="email"]')).to_have_count(1)
        assert head.evaluate(_TAGS) == 0, "the tag jumped to the address that is left"
        page.locator("[data-form-save]").click()
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        assert _household(other)["persons"]["Hoofd"]["emails"] == {other: False}
        assert page.errors == []
    finally:
        page.close()
        _remove(other)


def test_the_main_member_has_no_verwijderen_for_anyone(browser):
    """Rule 1 on the page: signed in as the partner, the main member is no row
    at all (#1632: a section, with nothing that folds or removes — the service
    refuses anyway); the partner's own row has no menu (nobody removes
    themselves); a person added does."""
    tag = uuid.uuid4().hex[:8]
    partner_mail = f"e2e.partner.{tag}@example.com"
    email = _sign_up(browser, tag, partner_email=partner_mail)
    page = _open(browser, "/leden/gezin?bewerken=1", session=_session(partner_mail))
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        rows = page.locator(PERSONS)
        menus = "> [data-row-body] > .group-fold-menu [data-row-menu-trigger]"
        head = page.locator(HEAD)
        expect(head.locator('input[name$=".first_name"]')).to_have_value("Hoofd")
        assert head.locator("[data-row-fold], .group-fold-menu").count() == 0
        expect(rows).to_have_count(1)
        assert rows.nth(0).locator(menus).count() == 0
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        assert rows.nth(1).locator(menus).count() == 1
        assert page.errors == []
    finally:
        page.close()
        _remove(email)


# ── #1632: the correction of 5 October 2026 on the two pages ─────────────────

_SHAPE = """() => { const r = e => { const b = e.getBoundingClientRect(); return {x: Math.round(b.left), y: Math.round(b.top + scrollY), w: Math.round(b.width)}; };
  const q = s => document.querySelector(s), head = q('#hoofdlid');
  const seen = e => e.checkVisibility() && e.getBoundingClientRect().width > 1;
  const said = [...head.querySelectorAll('[data-main-emails] label, [data-main-emails] p, [data-main-emails] span')]
    .filter(e => seen(e) && e.innerText.replace('*', '').trim() === 'E-mail').length;
  const mail = head.querySelector('[data-main-emails] input[type=email]');
  return {born: r(head.querySelector('[data-field$=".date_of_birth"]')), gender: r(head.querySelector('[data-field$=".gender_code"]')),
          gender_is: head.querySelector('[name$=".gender_code"]').tagName,
          tops: ['#hoofdlid', '#gezin-adres', '#gezinsleden'].map(s => r(q(s)).y),
          said, mail_name: mail ? mail.getAttribute('aria-label') : null, mail: mail ? r(mail) : null,
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["1440", "390"])
def test_the_main_member_first_the_address_next_and_the_fields_as_koen_asked(browser, viewport):
    """#1632 (CR-11 Q70–Q72), measured in edit mode. Red on master: the gender a
    radio group under the date, the address after the persons, the label
    "E-mail" on the row (on a phone above the field)."""
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag)
    page = _open(browser, "/leden/gezin?bewerken=1", viewport, session=_session(email))
    try:
        m = page.evaluate(_SHAPE)
        print("MEASURE household order", viewport["width"], m)
        assert m["tops"] == sorted(m["tops"]) and len(set(m["tops"])) == 3, (
            "the order of the sections"
        )
        assert m["gender_is"] == "SELECT"
        if viewport is DESKTOP:
            assert m["gender"]["y"] == m["born"]["y"], "Geslacht is not beside Geboortedatum"
            assert m["gender"]["x"] > m["born"]["x"] and m["gender"]["w"] == m["born"]["w"]
        else:
            assert m["gender"]["y"] > m["born"]["y"] and m["gender"]["x"] == m["born"]["x"]
        assert m["said"] == 0, "an e-mail row shows a label of its own"
        assert m["mail_name"] == "E-mail", "the field lost its accessible name"
        assert m["mail"]["w"] > 200, "the address field is not there to type in"
        assert m["page"] == [viewport["width"], viewport["width"]]
        assert page.errors == []
    finally:
        page.close()
        _remove(email)


def test_the_membership_card_shows_the_transfer_that_is_due(browser):
    """#1632 (Q73): a household that signed up by transfer reads what to pay in
    the Lidmaatschap card of Mijn gezin, on a phone, without leaving the page."""
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag, partner=False)
    page = _open(browser, "/leden/gezin", PHONE, session=_session(email))
    try:
        card = page.locator("[data-membership-status]")
        expect(card).to_contain_text("Je betaling loopt nog.")
        due = card.locator("[data-transfer-due]")
        expect(due).to_be_visible()
        expect(due).to_contain_text("Gestructureerde mededeling")
        expect(due).to_contain_text("+++")
        box, inner = card.bounding_box(), due.bounding_box()
        assert box["x"] <= inner["x"] and inner["x"] + inner["width"] <= box["x"] + box["width"]
        assert page.evaluate("document.documentElement.scrollWidth") == 390
        assert card.locator("text=✅").count() == 0
        # #1641 (Q79): the card is the one place — no link to a second screen,
        # and the renewal page lands here while the renewal runs.
        assert card.get_by_role("link").count() == 0
        page.goto("/leden/gezin/vernieuwen")
        pagina_klaar(page)
        assert page.url == f"{BASE}/leden/gezin"
    finally:
        page.close()
        _remove(email)


# ── #1641: the add button under the last item, one e-mail field, the inset ───

_ADD = """(group) => { const r = e => { const b = e.getBoundingClientRect(); return {top: Math.round(b.top + scrollY), bottom: Math.round(b.bottom + scrollY), x: Math.round(b.left), w: Math.round(b.width)}; };
  const g = document.querySelector(group), own = s => [...g.querySelectorAll(s)].filter(e => e.closest('[data-repeating-group]') === g);
  const rows = [...g.querySelectorAll(':scope > [data-group-rows] > [data-group-row]')], add = own('[data-group-add]');
  const head = g.querySelector(':scope > div'), empty = own('[data-group-empty]')[0];
  return {rows: rows.map(r), buttons: add.length, add: r(add[0]), head: r(head),
          empty: empty && empty.checkVisibility() ? r(empty) : null,
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["1440", "390"])
def test_gezinslid_toevoegen_stands_under_the_last_person_and_adds_above_itself(browser, viewport):
    """#1641 (CR-11 Q76). Red on master: the button stood in the group's head,
    above the first person. On Word lid the group is empty: the button stands
    where the first person will come, under the empty line."""
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag)
    page = _open(browser, "/leden/gezin?bewerken=1", viewport, session=_session(email))
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        m = page.evaluate(_ADD, "#gezinsleden")
        print("MEASURE add under last", viewport["width"], m)
        assert m["buttons"] == 1 and len(m["rows"]) == 1
        assert m["add"]["top"] >= m["rows"][-1]["bottom"], "the button is not under the last person"
        assert m["add"]["top"] > m["head"]["bottom"], "the button is still in the head"
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        expect(page.locator(PERSONS)).to_have_count(2)
        after = page.evaluate(_ADD, "#gezinsleden")
        assert after["rows"][-1]["bottom"] <= after["add"]["top"], "the new person is not above it"
        assert after["add"]["top"] > m["add"]["top"], "the button did not move down"
        assert after["page"] == [viewport["width"], viewport["width"]]
        # the e-mail group of a person keeps its button in its head
        mails = page.evaluate(_ADD, "#hoofdlid [data-repeating-group]")
        assert mails["add"]["top"] < mails["rows"][0]["top"], "the e-mail button left its head"
        assert page.errors == []
    finally:
        page.close()
        _remove(email)

    signup = _open(browser, "/lid-worden", viewport)
    try:
        s = signup.evaluate(_ADD, "#gezinsleden")
        assert s["rows"] == [] and s["empty"], "Word lid starts with an empty group"
        assert s["add"]["top"] >= s["empty"]["bottom"], "the button is not where the first comes"
        signup.get_by_role("button", name="Gezinslid toevoegen").click()
        expect(signup.locator(PERSONS)).to_have_count(1)
        s = signup.evaluate(_ADD, "#gezinsleden")
        assert s["rows"][0]["bottom"] <= s["add"]["top"]
    finally:
        signup.close()


def test_every_person_opens_with_one_email_field_and_an_empty_one_is_not_saved(browser):
    """#1641 (Q77). Red on master: the partner's group read "Nog geen
    e-mailadres." and a new person's had no field. Saving with the partner's
    field empty writes no address and refuses nothing."""
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag)
    page = _open(browser, "/leden/gezin?bewerken=1", PHONE, session=_session(email))
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        partner = page.locator(PERSONS).nth(0)
        partner.locator("summary").click()
        mail = partner.locator('input[type="email"]')
        expect(mail).to_have_count(1)
        expect(mail).to_be_visible()
        expect(mail).to_have_value("")
        assert mail.get_attribute("required") is None
        expect(partner.get_by_text("Nog geen e-mailadres.")).to_be_hidden()
        # "+ E-mailadres" adds a second one
        partner.locator("[data-repeating-group] [data-group-add]").click()
        expect(partner.locator('input[type="email"]')).to_have_count(2)
        # a person added in the page has one of their own
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        new = page.locator(PERSONS).nth(1)
        expect(new.locator('input[type="email"]')).to_have_count(1)
        new.locator(".group-fold-menu [data-row-menu-trigger]").click()
        new.locator(".group-fold-menu").get_by_role("menuitem", name="Verwijderen").click()

        page.fill("#address-street", "Legestraat")
        page.locator("[data-form-save]").click()
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        stored = _household(email)
        assert stored["persons"]["Partner"]["emails"] == {}, "an empty field became an address"
        assert stored["address"][0] == "Legestraat"
        assert page.errors == []
    finally:
        page.close()
        _remove(email)

    # Word lid: the main member's empty field is refused, with the message on the field
    signup = _open(browser, "/lid-worden", PHONE)
    try:
        fill_person(signup.locator(HEAD), "Zonder", f"Adres {tag}")
        signup.locator(HEAD).locator('input[name$=".mobile"]').fill("0470000000")
        signup.fill("#address-street", "Teststraat")
        signup.fill("#address-house_number", "1")
        signup.select_option("#address-postal_code", index=1)
        signup.check('input[name="payment_method"][value="transfer"]')
        signup.locator("[data-form-save]").click()
        field = signup.locator(HEAD).locator('input[type="email"]')
        expect(field).to_have_attribute("aria-invalid", "true")
        expect(field).to_be_focused()
        expect(signup.locator(HEAD)).to_contain_text(
            "E-mailadres is verplicht voor het hoofdgezinslid."
        )
    finally:
        signup.close()


_INSET = """() => { const card = document.querySelector('[data-membership-status]'), inset = card.querySelector('[data-inset]');
  const c = card.getBoundingClientRect(), b = inset.getBoundingClientRect(), s = getComputedStyle(inset);
  const first = inset.firstElementChild.getBoundingClientRect();
  return {card: [Math.round(c.left), Math.round(c.width)], box: [Math.round(b.left), Math.round(b.top + scrollY), Math.round(b.width), Math.round(b.height)],
          padding: [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft], radius: s.borderTopLeftRadius,
          tint: s.backgroundColor, border: s.borderTopWidth, shadow: s.boxShadow,
          title: inset.querySelector('[data-inset-title]').innerText, inner: Math.round(first.left - b.left),
          lines: [...inset.querySelectorAll('li')].map(li => li.innerText.split(':')[0]),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["1440", "390"])
def test_the_transfer_stands_in_the_card_as_an_inset_of_the_kit(browser, viewport):
    """#1641 point 4 (Q79), the box and its padding measured. Red on master: loose
    lines in the card, no inset."""
    tag = uuid.uuid4().hex[:8]
    email = _sign_up(browser, tag, partner=False)
    page = _open(browser, "/leden/gezin", viewport, session=_session(email))
    try:
        m = page.evaluate(_INSET)
        print("MEASURE inset", viewport["width"], m)
        # #1737: one sentence for a first membership and a renewal alike.
        assert m["title"] == "Lidmaatschap geregistreerd — betaal via overschrijving:"
        assert m["padding"] == ["16px"] * 4 and m["radius"] == "6px"
        assert m["tint"] not in ("rgb(255, 255, 255)", "rgba(0, 0, 0, 0)"), "no tint"
        assert m["border"] == "0px" and m["shadow"] == "none", "an inset is no card"
        assert m["inner"] == 16
        # inside the card, with the card's own 16 px on both sides
        assert m["box"][0] == m["card"][0] + 17 and m["box"][2] == m["card"][1] - 34, m
        assert m["lines"][0] == "Bedrag" and m["lines"][-1] == "Te betalen vóór"
        assert "Gestructureerde mededeling" in m["lines"]
        assert m["page"] == [viewport["width"], viewport["width"]]
    finally:
        page.close()
        _remove(email)

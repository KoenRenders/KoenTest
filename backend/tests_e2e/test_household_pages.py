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
  "Vernieuwen en betalen" on the renewal);
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
    from app.domains.membership.api import delete_family

    stored = _household(email)
    if stored is None:
        return
    db = _db()
    try:
        delete_family(db, stored["member_id"], admin=SimpleNamespace(email="e2e-1590@example.com"))
    finally:
        db.close()


def _sign_up(browser, tag: str, *, partner: bool = True) -> str:
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
        # ── As it opens: one person, open; a postal code that is a select ──
        assert page.evaluate(_FOLDS) == [True]
        assert page.locator("#address-postal_code").evaluate("e => e.tagName") == "SELECT"
        bar = page.evaluate(_BAR)
        assert bar["width"] == 390, f"the page scrolls sideways: {bar}"
        assert bar["bottom"] == bar["window"], f"the bar does not stand at the bottom: {bar}"
        assert page.locator("text=Verplicht veld").count() == 0
        assert page.locator("[data-member-nudge]").count() == 0, "Word lid carries no nudge"

        # ── A person added: open, focused, and a partner by the one rule ──
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        rows = page.locator(PERSONS)
        expect(rows).to_have_count(2)
        partner = rows.nth(1)
        assert page.evaluate("document.activeElement.name").endswith(".first_name")
        assert partner.locator('input[name$=".first_name"]').evaluate(
            "e => e === document.activeElement"
        )
        expect(partner.locator('select[name$=".relation_type"]')).to_have_value("PARTNER")
        expect(partner.locator("[data-row-title-prefix]")).to_have_text("Partner")
        # the next one is a child: the rule is asked, not copied
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        child = rows.nth(2)
        expect(child.locator('select[name$=".relation_type"]')).not_to_have_value("PARTNER")
        expect(child.locator('select[name$=".relation_type"]')).not_to_have_value("")
        # the title follows the names
        fill_person(partner, "Marie", f"Rijen {tag}", gender="F")
        expect(partner.locator("[data-row-title]")).to_have_text(f"Marie Rijen {tag}")

        # ── A row that was never saved goes without a question ──
        child.locator("[data-row-menu-trigger]").click()
        child.get_by_role("menuitem", name="Verwijderen").click()
        expect(rows).to_have_count(2)
        assert page.locator("[data-dialog]:visible").count() == 0, (
            "removing an unsaved row asked something"
        )

        # ── The main member's addresses: one tag, and it moves ──
        head = rows.first
        fill_person(head, "E2E", f"Rijen {tag}")
        head.locator('input[name$=".mobile"]').fill("0470000000")
        head.locator('input[type="email"]').first.fill(first)
        assert head.evaluate(_TAGS) == 1
        assert head.locator("[data-row-menu-trigger]:visible").count() == 0, (
            "the main address offers a menu — it cannot be removed"
        )
        head.get_by_role("button", name="E-mailadres").click()
        mails = head.locator('input[type="email"]')
        expect(mails).to_have_count(2)
        mails.nth(1).fill(second)
        assert head.evaluate(_TAGS) == 1, "the tag stands on two rows"
        head.locator("[data-row-menu-trigger]:visible").click()
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
        assert page.evaluate(_FOLDS) == [True, False]
        page.fill("#address-street", "Teststraat")
        page.fill("#address-house_number", "1")
        page.posts.clear()
        save.click()
        banner = page.locator("[data-save-refusal]")
        expect(banner).to_be_visible()
        expect(banner).to_contain_text("Verzenden kan nog niet: controleer 2 velden.")
        refused = partner.locator('input[name$=".first_name"]')
        expect(refused).to_be_visible()
        assert page.evaluate(_FOLDS) == [True, True], "the refused row stayed folded"
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
        assert page.evaluate(_FOLDS) == [True, False]
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
        head = rows.first
        head.locator('input[name$=".first_name"]').fill("Theo")
        head.get_by_role("button", name="E-mailadres").click()
        head.locator('input[type="email"]').nth(1).fill(new_mail)
        page.fill("#address-street", "Nieuwstraat")
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        fill_person(rows.nth(2), "Kind", f"Gezin {tag}", born="2015-05-05", gender="F")

        page.posts.clear()
        page.locator("[data-form-save]").click()

        # ── One request; read mode again; the toast; the values ──
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        expect(page.locator("#toasts")).to_contain_text("Opgeslagen ✓")
        assert page.posts == [f"{BASE}/leden/gezin"], page.posts
        assert page.url == f"{BASE}/leden/gezin"
        expect(page.locator(PERSONS)).to_have_count(3)
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
        assert page.evaluate(_FOLDS) == [True, False]
        # the partner's row is folded; its first name is emptied without opening it
        rows.nth(1).locator('input[name$=".first_name"]').evaluate(
            "e => { e.value = ''; e.dispatchEvent(new Event('input', {bubbles: true})); }"
        )
        page.fill("#address-street", "Blijfstraat")
        page.locator("[data-form-save]").click()

        banner = page.locator("[data-save-refusal]")
        expect(banner).to_contain_text("Opslaan kan nog niet: controleer 1 veld.")
        refused = rows.nth(1).locator('input[name$=".first_name"]')
        expect(refused).to_be_visible()
        expect(refused).to_be_focused()
        assert page.evaluate(_FOLDS) == [True, True]
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
            expect(page.get_by_role("heading", name="Lidmaatschap vernieuwen")).to_be_visible()
            expect(page.locator("[data-renewal-status]")).to_contain_text(
                "geen geldig lidmaatschap"
            )
            terms = page.locator("[data-membership-terms]")
            expect(terms).to_contain_text("€")
            expect(terms).to_contain_text("Geldig tot en met")
            save = page.locator("[data-form-save]")
            expect(save.locator("[data-save-idle]")).to_have_text("Vernieuwen en betalen")
            page.check('input[name="payment_method"][value="transfer"]')
            expect(save.locator("[data-save-idle]")).to_have_text("Lidmaatschap vernieuwen")
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

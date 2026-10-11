"""E2E: the board's household record in the browser (#1899, CR-11 roll-out slice 1;
end state §2.2, §5.2).

- **Read first**: the record head with Bewerken and Acties, the tabs, the
  summary card, a card per person, Adres, Verantwoordelijk bestuurslid and
  Lidmaatschapsjaren — at 1440 and at 390 px no wider than the window;
- **one save**: in edit mode a changed address, a person added, an e-mail
  address added and a year removed go with ONE "Opslaan" — one request — and
  the record answers in read mode with the toast; what is stored is read in a
  session of our own;
- **a refusal** stands at its field, keeps what was typed and writes nothing —
  also not the year that was removed in the same form;
- **measured in edit mode**: the `⋯` of every e-mail row on one x, the e-mail
  fields equally wide, the address on the kit's grid;
- **Lidmaatschap vernieuwen** (§4): from Acties to the renewal page in the
  admin shell; the transfer choice lands on the record, where the running
  renewal stands and Acties offers no second one.

On master the record is eight cards with a form each; there is no
`#gezin-form` and no `?bewerken=1`.
"""

import os
import sys
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, fill_person, login_als_admin, pagina_klaar  # noqa: E402

PERSONS = "#gezinsleden > [data-group-rows] > [data-group-row]"
HEAD = "#hoofdlid"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _db():
    import app.main  # noqa: F401  the whole app, so the domain facades import in order
    from app.database import SessionLocal

    return SessionLocal()


def _board(browser, width: int, height: int):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.posts = []
    page.on("request", lambda r: page.posts.append(r.url) if r.method == "POST" else None)
    login_als_admin(page, email, make_session_value(email))
    return page


@pytest.fixture
def household():
    """A household of our own: a main member with two e-mail addresses and an
    address, a partner with one, and two membership years without a booking.
    Gone again afterwards."""
    from app.domains.mdm.api import (
        Address,
        ContactDetail,
        Member,
        MemberPerson,
        Person,
        PostalCode,
        delete_household,
    )
    from app.domains.membership.api import Membership

    tag = uuid.uuid4().hex[:8]
    db = _db()
    try:
        postal = db.query(PostalCode).first()
        member = Member()
        db.add(member)
        db.flush()
        people = {}
        for key, first, relation in (("main", "Hanne", "HOOFDLID"), ("partner", "Bram", "PARTNER")):
            person = Person(
                first_name=first,
                last_name=f"Record-{tag}",
                date_of_birth=date(1980, 3, 4),
                gender_code="F" if key == "main" else "M",
            )
            db.add(person)
            db.flush()
            db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type=relation))
            people[key] = person
        for number, primary in ((1, True), (2, False)):
            db.add(
                ContactDetail(
                    person_id=people["main"].id,
                    contact_type_code="EMAIL",
                    value=f"record-{tag}-{number}@example.org",
                    is_primary=primary,
                )
            )
        db.add(
            ContactDetail(
                person_id=people["partner"].id,
                contact_type_code="EMAIL",
                value=f"record-{tag}-p@example.org",
                is_primary=True,
            )
        )
        db.add(
            Address(
                person_id=people["main"].id,
                street="Voorbeeldstraat",
                house_number="12",
                postal_code_id=postal.id,
            )
        )
        for year in (2019, 2020):
            db.add(
                Membership(
                    member_id=member.id,
                    year=year,
                    is_active=True,
                    valid_from=date(year, 1, 1),
                    valid_to=date(year, 12, 31),
                )
            )
        db.commit()
        made = {
            "id": member.id,
            "tag": tag,
            "main": people["main"].id,
            "partner": people["partner"].id,
        }
    finally:
        db.close()
    yield made
    db = _db()
    try:
        if db.query(Member).filter(Member.id == made["id"]).first() is not None:
            delete_household(db, made["id"], admin=SimpleNamespace(email="e2e-1899@example.com"))
    finally:
        db.close()


def _queued_mails(address: str) -> list[dict]:
    """The messages that wait in the job queue for this address."""
    from app.kernel.jobs import KernelJob

    db = _db()
    try:
        jobs = db.query(KernelJob).filter(KernelJob.name == "mail.send").all()
        return [j.payload for j in jobs if (j.payload or {}).get("to_email") == address]
    finally:
        db.close()


def _stored(household_id: int) -> dict:
    from app.domains.mdm.api import Member
    from app.domains.membership.api import Membership

    db = _db()
    try:
        member = db.query(Member).filter(Member.id == household_id).one()
        persons = {}
        street = None
        for link in member.member_persons:
            if link.deleted_at is not None:
                continue
            p = link.person
            persons[p.first_name] = {
                "relation": link.relation_type.value,
                "emails": sorted(
                    c.value for c in p.contact_details if c.contact_type_code == "EMAIL"
                ),
            }
            if p.address is not None:
                street = p.address.street
        years = sorted(
            m.year for m in db.query(Membership).filter(Membership.member_id == household_id)
        )
        return {"persons": persons, "street": street, "years": years}
    finally:
        db.close()


READ = """() => { const q = s => document.querySelector(s), all = s => [...document.querySelectorAll(s)];
  const first = q('[data-form-flow] [data-form-section]');
  return {mode: q('[data-form-flow]').dataset.mode, title: q('[data-record-head] h1').innerText.trim(),
          primary: (q('[data-record-head] a[href*="bewerken=1"]') || {innerText: ''}).innerText.trim(),
          tabs: all('[data-related-tabs] a').map(a => a.innerText.trim().replace(/\\s+/g, ' ')),
          figures: all('[data-summary-card] dt').map(e => e.innerText.trim()),
          cards: all('[data-person-card]').length,
          sections: all('[data-form-flow] h2').map(h => h.innerText.trim()),
          years: all('[data-membership-year]').map(e => e.dataset.membershipYear),
          controls: all('#gezin-record [data-form-flow] input:not([type=hidden]), #gezin-record [data-form-flow] select').length,
          gaps: all('[data-form-flow] .form-section').filter(e => !e.parentElement.closest('.form-section')).map(e => e.getBoundingClientRect())
                 .map((b, i, a) => i ? Math.round(b.top - a[i - 1].bottom) : null).filter(g => g !== null),
          first_card_y: first ? Math.round(first.getBoundingClientRect().top + scrollY) : null,
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (390, 844)])
def test_the_record_reads_first(browser, household, width, height):
    page = _board(browser, width, height)
    try:
        page.goto(f"/admin/leden/gezin/{household['id']}")
        pagina_klaar(page)
        seen = page.evaluate(READ)
        print("MEASURE household record read", width, seen)
        assert seen["mode"] == "read" and seen["controls"] == 0, "the record opens with a control"
        assert seen["title"] == f"Record-{household['tag']} Hanne" and seen["primary"] == "Bewerken"
        assert [t.split(" (")[0] for t in seen["tabs"]] == [
            "Gegevens",
            "Inschrijvingen",
            "Betalingen",
        ]
        assert seen["figures"] == ["Personen", "Openstaand"], seen["figures"]
        assert seen["cards"] == 2, "a card per person"
        # The person cards carry their person's name; these three keep a title.
        assert [s for s in seen["sections"] if "Record-" not in s] == [
            "Adres",
            "Verantwoordelijk bestuurslid",
            "Lidmaatschapsjaren",
        ], seen["sections"]
        assert seen["years"] == ["2020", "2019"], "the newest year first"
        assert set(seen["gaps"]) == {16}, f"16 px between the cards: {seen['gaps']}"
        assert seen["page"][0] == seen["page"][1], "wider than the window"
        assert page.errors == []
    finally:
        page.close()


def test_one_opslaan_writes_the_whole_household(browser, household):
    tag = household["tag"]
    new_mail = f"record-{tag}-nieuw@example.org"
    page = _board(browser, 1440, 900)
    try:
        page.goto(f"/admin/leden/gezin/{household['id']}")
        pagina_klaar(page)
        page.get_by_role("link", name="Bewerken").click()
        pagina_klaar(page)
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "edit")
        expect(page.locator("[data-action-bar]")).to_have_count(1)
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")

        # the address, a person, an e-mail address, a year
        page.fill("#address-street", "Nieuwstraat")
        page.get_by_role("button", name="Gezinslid toevoegen").click()
        rows = page.locator(PERSONS)
        expect(rows).to_have_count(2)
        fill_person(rows.nth(1), "Kim", f"Record-{tag}", born="2015-05-05", gender="F")
        partner = rows.nth(0)
        partner.locator("[data-repeating-group] [data-group-add]").click()
        partner.locator('input[type="email"]').nth(1).fill(new_mail)
        years = page.locator("#gezin-jaren [data-group-rows] > [data-group-row]")
        expect(years).to_have_count(2)
        years.nth(1).locator("[data-row-menu-trigger]").click()
        years.nth(1).get_by_role("menuitem", name="Verwijderen").click()
        expect(years).to_have_count(1)
        assert page.locator("[data-dialog]:visible").count() == 0, "removing a row asked something"

        page.posts.clear()
        page.locator("[data-form-save]").click()

        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        expect(page.locator("#toasts")).to_contain_text("Opgeslagen ✓")
        assert page.posts == [f"{BASE}/admin/leden/gezin/{household['id']}"], page.posts
        assert page.url == f"{BASE}/admin/leden/gezin/{household['id']}"
        expect(page.locator("[data-person-card]")).to_have_count(3)
        expect(page.locator("[data-address-line]")).to_contain_text("Nieuwstraat 12")
        assert page.errors == []

        stored = _stored(household["id"])
        assert stored["street"] == "Nieuwstraat"
        assert set(stored["persons"]) == {"Hanne", "Bram", "Kim"}
        assert stored["persons"]["Bram"]["emails"] == sorted(
            [f"record-{tag}-p@example.org", new_mail]
        )
        assert stored["years"] == [2020], "the removed year is still there"
    finally:
        page.close()


def test_a_refusal_stands_at_its_field_and_writes_nothing(browser, household):
    page = _board(browser, 390, 844)
    try:
        page.goto(f"/admin/leden/gezin/{household['id']}?bewerken=1")
        pagina_klaar(page)
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        partner = page.locator(PERSONS).nth(0)
        partner.locator('input[name$=".first_name"]').fill("")
        page.fill("#address-street", "Blijfstraat")
        years = page.locator("#gezin-jaren [data-group-rows] > [data-group-row]")
        years.nth(0).locator("[data-row-menu-trigger]").click()
        years.nth(0).get_by_role("menuitem", name="Verwijderen").click()
        page.locator("[data-form-save]").click()

        banner = page.locator("[data-save-refusal]")
        expect(banner).to_contain_text("Opslaan kan nog niet: controleer 1 veld.")
        refused = partner.locator('input[name$=".first_name"]')
        expect(refused).to_be_focused()
        expect(refused).to_have_attribute("aria-invalid", "true")
        expect(page.locator("#address-street")).to_have_value("Blijfstraat")
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "edit")
        assert page.evaluate("document.documentElement.scrollWidth") == 390
        stored = _stored(household["id"])
        assert stored["street"] == "Voorbeeldstraat", "a refused save wrote the address"
        assert stored["years"] == [2019, 2020], "a refused save removed the year"
        assert set(stored["persons"]) == {"Hanne", "Bram"}
    finally:
        page.close()


EDIT = """() => { const r = e => e.getBoundingClientRect(), n = v => Math.round(v);
  const head = document.querySelector('#hoofdlid');
  const rows = [...head.querySelectorAll('[data-repeating-group^="e_order."] [data-group-rows] > [data-group-row]')];
  const box = id => r(document.getElementById(id));
  return {menus: rows.map(row => n(r(row.querySelector('[data-row-menu-trigger]')).left)),
          fields: rows.map(row => n(r(row.querySelector('input[type=email]')).width)),
          tags: rows.map(row => [...row.querySelectorAll('[data-row-one-tag]')].filter(t => t.checkVisibility()).length),
          address: {street: n(box('address-street').width), house: n(box('address-house_number').width), bus: n(box('address-bus_number').width),
                    tops: ['address-street', 'address-house_number', 'address-bus_number'].map(id => n(box(id).top))},
          relation: !!head.querySelector('select[name$=".relation_type"]'),
          selects: document.querySelectorAll('#gezinsleden select[name$=".relation_type"]').length,
          bar: n(r(document.querySelector('[data-action-bar]')).bottom), window: innerHeight,
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


def test_the_board_renews_from_the_record(browser, household):
    """#1899 §4, in the browser at 390 px: Acties → Lidmaatschap vernieuwen is the
    renewal page in the admin shell; a transfer is ONE request and lands on the
    record with the running renewal — no second renewal on offer. And the
    household's main member is mailed the confirmation (#1903), at his main
    address: read where the mail waits, the queue — the server of the browser
    tests runs no jobs, so nothing reaches the mail log there.

    Proven red (locally, restored): `hx-post` of the shared form pointed at a
    path that does not exist → no request reaches the board's route and the
    test falls waiting for the record."""
    page = _board(browser, 390, 844)
    renew = f"/admin/leden/gezin/{household['id']}/vernieuwen"
    try:
        page.goto(f"/admin/leden/gezin/{household['id']}")
        pagina_klaar(page)
        page.get_by_role("button", name="Acties").click()
        page.get_by_role("menuitem", name="Lidmaatschap vernieuwen").click()
        page.wait_for_url(f"**{renew}")
        pagina_klaar(page)
        expect(page.locator("body")).to_have_attribute("data-shell", "admin")
        expect(page.locator("#vernieuw-form")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth") == 390

        page.locator('input[name="payment_method"][value="transfer"]').check()
        page.posts.clear()
        page.locator("[data-form-save]").first.click()
        page.wait_for_url(f"**/admin/leden/gezin/{household['id']}")
        pagina_klaar(page)

        assert [u for u in page.posts if u.endswith(renew)] == [BASE + renew], page.posts
        expect(page.locator("[data-renewal-running]")).to_be_visible()
        expect(page.locator("[data-renewal-running] [data-transfer-due]")).to_be_visible()
        page.get_by_role("button", name="Acties").click()
        expect(page.get_by_role("menuitem", name="Verwijderen")).to_be_visible()
        expect(page.get_by_role("menuitem", name="Lidmaatschap vernieuwen")).to_have_count(0)
        expect(page.locator("[data-renewal-unmailed]")).to_have_count(0)
        assert page.errors == []
        queued = _queued_mails(f"record-{household['tag']}-1@example.org")
        assert len(queued) == 1, f"{len(queued)} mails wait for the main member"
        assert "Betaalinstructies (overschrijving)" in queued[0]["body_html"]
        assert "lidmaatschap" in queued[0]["subject"].lower()
    finally:
        page.close()


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (390, 844)])
def test_the_summary_is_rows_to_read_and_gone_while_editing(browser, household, width, height):
    """The summary card has one shape (Koen, 11 October 2026: "B voor elke kaart"):
    every figure a row, label left and value right, the values on one right edge
    — in the card beside the form and in the strip on a phone alike. And on the
    household's record it is not there while editing (Koen, the same day: "ja",
    and "b" — the household only): the first input field then stands a card
    higher on a phone.

    Proven red (locally, restored): the `{% if not edit %}` around the card
    replaced by `{% if true %}` → "the summary stands above the editor"; the
    figure's `display:flex` renamed in the css → "label and value do not share
    a line"."""
    page = _board(browser, width, height)
    try:
        page.goto(f"/admin/leden/gezin/{household['id']}")
        pagina_klaar(page)
        read = page.evaluate(
            """() => { const r = e => e.getBoundingClientRect();
              const mid = b => Math.round(b.top + b.height / 2);
              const card = document.querySelector('[data-summary-card]');
              return {cards: document.querySelectorAll('[data-summary-card]').length,
                      figures: [...card.querySelectorAll('[data-summary-figure]')].map(f => {
                        const label = r(f.querySelector('dt')), value = r(f.querySelector('dd'));
                        return {label: [Math.round(label.left), mid(label)], value: [Math.round(value.right), mid(value)],
                                apart: Math.round(value.left - label.right)}; }),
                      card: [Math.round(r(card).left), Math.round(r(card).right)]}; }"""
        )
        print("MEASURE summary read", width, read)
        assert read["cards"] == 1 and len(read["figures"]) >= 1
        for figure in read["figures"]:
            assert abs(figure["label"][1] - figure["value"][1]) <= 3, (
                "label and value do not share a line"
            )
            assert figure["apart"] >= 12, "the value runs into its label"
        assert len({f["label"][0] for f in read["figures"]}) == 1, "the labels share no left edge"
        assert len({f["value"][0] for f in read["figures"]}) == 1, "the values share no right edge"

        page.goto(f"/admin/leden/gezin/{household['id']}?bewerken=1")
        pagina_klaar(page)
        edit = page.evaluate(
            """() => { const first = document.querySelector('#gezin-form input:not([type=hidden])').getBoundingClientRect();
              const bar = document.querySelector('[data-action-bar]').getBoundingClientRect();
              return {cards: document.querySelectorAll('[data-summary-card]').length,
                      column: !!document.querySelector('[data-summary-column]'),
                      first_input: [Math.round(first.top), Math.round(first.bottom)], bar_top: Math.round(bar.top),
                      window: innerHeight, page: [document.documentElement.scrollWidth, innerWidth]}; }"""
        )
        print("MEASURE summary edit", width, edit)
        assert edit["cards"] == 0 and not edit["column"], "the summary stands above the editor"
        assert edit["page"][0] == edit["page"][1]
        if width == 390:
            # It stood at y 615 with the strip above it; the bar starts at 723.
            assert edit["first_input"][0] < 520, (
                f"the first field starts at {edit['first_input'][0]}"
            )
    finally:
        page.close()


def test_no_line_of_the_heads_facts_ends_on_a_separator(browser, household):
    """The head's facts — address · e-mail address — wrap on a narrow phone. The
    fact that starts a line shows no separator, and no line ends on one: every
    separator that can be seen stands between two facts of its line.

    Proven red (locally, restored): the clip taken off the line (`overflow-x-clip`
    renamed) → "a separator starts a line"."""
    page = _board(browser, 320, 700)
    try:
        page.goto(f"/admin/leden/gezin/{household['id']}")
        pagina_klaar(page)
        seen = page.evaluate(
            """() => { const line = document.querySelector('[data-facts]');
              const edge = line.getBoundingClientRect().left;
              const facts = [...line.querySelectorAll('[data-fact]')].map(f => {
                const mark = f.querySelector('[data-fact-dot]'), dot = mark.getBoundingClientRect();
                const box = f.getBoundingClientRect();
                // What is clipped away is not hit: the point in the dot's middle then finds something else.
                const hit = document.elementFromPoint(dot.left + dot.width / 2, dot.top + dot.height / 2);
                return {top: Math.round(box.top), dot_visible: hit === mark,
                        dot_left: Math.round(dot.left - edge)}; });
              return {facts, clip: getComputedStyle(line).overflowX,
                      page: [document.documentElement.scrollWidth, innerWidth]}; }"""
        )
        print("MEASURE head facts 320", seen)
        facts = seen["facts"]
        assert len(facts) == 2, "the household's head shows its address and its e-mail address"
        assert facts[0]["top"] < facts[1]["top"], "the facts fit on one line — this proves nothing"
        for fact in facts:
            assert not fact["dot_visible"], "a separator starts a line"
        assert seen["page"][0] == seen["page"][1], "the head is wider than the window"
    finally:
        page.close()

    wide = _board(browser, 1440, 900)
    try:
        wide.goto(f"/admin/leden/gezin/{household['id']}")
        pagina_klaar(wide)
        dots = wide.evaluate(
            """() => { const line = document.querySelector('[data-facts]');
              return [...line.querySelectorAll('[data-fact-dot]')].map(d => { const b = d.getBoundingClientRect();
                return document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2) === d; }); }"""
        )
        assert dots == [False, True], f"on one line the separator stands between the two: {dots}"
    finally:
        wide.close()


def test_on_a_phone_a_year_stands_beside_its_menu(browser, household):
    """A membership year is a line of text, no field: on a phone its `⋯` stands on
    that line, at the right, where the kit gives a field's menu the row above it.

    Proven red (locally, restored): `data-row-inline` renamed in the css rule →
    "the menu stands 48 px above its year"."""
    page = _board(browser, 390, 844)
    try:
        page.goto(f"/admin/leden/gezin/{household['id']}?bewerken=1")
        pagina_klaar(page)
        rows = page.evaluate(
            """() => [...document.querySelectorAll('#gezin-jaren [data-group-row]')].map(row => {
              const mid = e => { const b = e.getBoundingClientRect(); return Math.round(b.top + b.height / 2); };
              const year = row.querySelector('[data-membership-year]');
              const menu = row.querySelector('[data-row-menu-holder]');
              return {year: mid(year), menu: mid(menu),
                      right: Math.round(menu.getBoundingClientRect().left - year.getBoundingClientRect().right)};
            })"""
        )
        print("MEASURE membership years 390", rows)
        assert rows, "no membership year on the record — still looking?"
        for row in rows:
            apart = abs(row["year"] - row["menu"])
            assert apart <= 2, f"the menu stands {apart} px above its year"
            assert row["right"] >= 0, "the menu overlaps the year's line"
        assert page.evaluate("document.documentElement.scrollWidth") == 390
    finally:
        page.close()


def test_the_edit_mode_lines_up(browser, household):
    """The two positions that must line up (#1899): the `⋯` of every e-mail row on
    one x, and the e-mail fields equally wide — whatever tag a row carries."""
    page = _board(browser, 1440, 900)
    try:
        page.goto(f"/admin/leden/gezin/{household['id']}?bewerken=1")
        pagina_klaar(page)
        seen = page.evaluate(EDIT)
        print("MEASURE household record edit 1440", seen)
        assert len(seen["menus"]) == 2 and len(set(seen["menus"])) == 1, seen["menus"]
        assert len(set(seen["fields"])) == 1, f"the e-mail fields differ in width: {seen['fields']}"
        assert seen["tags"] == [1, 0], "the main address carries the tag, the other none"
        a = seen["address"]
        assert len(set(a["tops"])) == 1, "street, house number and bus stand on one line"
        assert a["house"] == a["bus"] and abs(a["street"] - (2 * a["house"] + 12)) <= 1, a
        assert not seen["relation"], "the main member is offered a relation"
        assert seen["selects"] == 1, "the partner's relation is a select in its title line"
        assert seen["bar"] == seen["window"], "the action bar does not stand at the window's bottom"
        assert seen["page"][0] == seen["page"][1]
    finally:
        page.close()

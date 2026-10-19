"""E2E #1900 (CR-11 roll-out, slice 2; end state §5.2): the activity record laid
against the household record.

- **Read mode shows facts and cards**: two cards (Activiteit, Intern), the dates,
  a heading "Onderdelen" above a card per component, the organisers — no
  control anywhere, 16 px between the cards, a filled external link as a fact
  line in the card of its component, a detail that is not shown reads "niet
  getoond"; no wider than the window at 1 440 and 390 px.
- **Edit mode lines up** (the two positions the issue names): the handle and
  the title on one line in every card and row; the `⋯` of every row of a group
  on one x.
- **The links open in place** and the one save writes them — also for a
  component that was added in the page.
- **A switched-off address is kept**: the field beside a switch that is off is
  read-only and looks switched off, and the save keeps the other address that
  was stored (a disabled field is not sent, and the save would erase it).

Proven red (locally, restored), each by an addition:
- `open` on the kit's `rare_line` → "a closed line shows its fields";
- `:disabled` beside `:readonly` on the organiser's e-mail field → "the field is
  disabled: it would not be sent";
- `card=False` passed to the component's row → "a component is not a card".
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

TAG = uuid.uuid4().hex[:6]
NAME = f"Zomerfeest 1900 {TAG}"


def _db():
    import app.main  # noqa: F401
    from app.database import SessionLocal

    return SessionLocal()


def _seed() -> dict:
    from decimal import Decimal

    from app.domains.activities.api import (
        Activity,
        ActivityDate,
        ActivityProduct,
        ActivitySubRegistration,
        add_organiser,
        update_organiser,
    )
    from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person

    db = _db()
    try:
        activity = Activity(name=NAME, location="Parochiezaal", description="Een feest.")
        db.add(activity)
        db.flush()
        db.add(ActivityDate(activity_id=activity.id, start_date=date(2031, 6, 27)))
        components = []
        for order, (name, link) in enumerate(
            (("Wandeling", "https://example.org/wandeling"), ("Fietstocht", None))
        ):
            component = ActivitySubRegistration(
                activity_id=activity.id,
                name=name,
                registration_type_code="INDIVIDUAL",
                price=0,
                is_free=True,
                sort_order=order,
                info_url=link,
            )
            db.add(component)
            db.flush()
            components.append(component.id)
            for n, product in enumerate(("Volwassene", "Kind")):
                db.add(
                    ActivityProduct(
                        component_id=component.id,
                        name=product,
                        price=Decimal("5.00"),
                        is_free=False,
                        sort_order=n,
                    )
                )

        def member(first_name: str, email: str, mobile: str) -> int:
            person = Person(
                date_of_birth=date(1980, 1, 1),
                gender_code="F",
                first_name=first_name,
                last_name=f"Trekker-{TAG}",
            )
            db.add(person)
            db.flush()
            household = Member()
            db.add(household)
            db.flush()
            db.add(
                MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID")
            )
            db.add(ContactDetail(party_id=person.party_id, contact_type_code="EMAIL", value=email))
            db.add(
                ContactDetail(party_id=person.party_id, contact_type_code="MOBILE", value=mobile)
            )
            db.flush()
            return person.id

        shown = add_organiser(db, activity.id, member("An", f"an-{TAG}@example.org", "0470000011"))
        hidden = add_organiser(
            db, activity.id, member("Jef", f"jef-{TAG}@example.org", "0470000012")
        )
        update_organiser(
            db,
            activity.id,
            shown.id,
            {"is_contact": True, "email_override": f"feest-{TAG}@example.org"},
        )
        update_organiser(db, activity.id, hidden.id, {"show_mobile": False})
        db.commit()
        return {
            "id": activity.id,
            "components": components,
            "shown": shown.id,
            "hidden": hidden.id,
        }
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.activities import service
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    made = _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), made
        b.close()
    db = _db()
    try:
        service.delete_activity(db, made["id"], actor="e2e-1900@example.com")
    finally:
        db.close()


def _page(setup, width: int, edit: bool = False):
    b, session, made = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.posts = []
    page.on("request", lambda r: page.posts.append(r.url) if r.method == "POST" else None)
    login_met_sessie(page, session)
    page.goto(f"/admin/activiteiten/{made['id']}" + ("?bewerken=1" if edit else ""))
    pagina_klaar(page)
    return page


_READ = """() => { const q = s => document.querySelector(s), all = s => [...document.querySelectorAll(s)];
  const r = e => { const b = e.getBoundingClientRect(); return {top: Math.round(b.top + scrollY), bottom: Math.round(b.bottom + scrollY)}; };
  const flow = q('[data-form-flow]');
  const cards = all('#aa-group-components > [data-group-rows] > [data-group-row]');
  const blocks = [q('#aa-section-activity'), q('#aa-section-internal'), q('#aa-group-dates'), ...cards, q('#aa-group-organisers')];
  return {mode: flow.dataset.mode,
          controls: flow.querySelectorAll('input, select, textarea, [data-row-handle], [data-row-menu-trigger], details').length,
          sections: all('#aa-detail h2').map(h => h.innerText.trim()),
          cards: cards.map(c => ({card: c.classList.contains('group-row--card'), title: c.querySelector('[data-row-title]').innerText.trim(),
                                  badge: c.querySelector('[data-occupancy]').innerText.trim(),
                                  links: [...c.querySelectorAll('[data-external-link]')].map(e => e.innerText.trim()),
                                  products: [...c.querySelectorAll('[data-product-line]')].map(e => e.innerText.replace(/\u00a0/g, ' ').trim())})),
          gaps: blocks.slice(1).map((b, i) => r(b).top - r(blocks[i]).bottom),
          heading: [r(q('[data-flow-heading]')).bottom, r(cards[0]).top],
          organisers: all('#aa-group-organisers [data-group-row]').map(o => ({
              state: o.querySelector('[data-contact-state]').innerText.trim(),
              facts: [...o.querySelectorAll('[data-organiser-facts] [data-icon-fact]')].map(e => e.innerText.trim())})),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("width", [1440, 390])
def test_read_mode_shows_facts_and_a_card_per_component(setup, width):
    page = _page(setup, width)
    try:
        seen = page.evaluate(_READ)
        print("MEASURE activity read", width, seen)
        assert seen["mode"] == "read" and seen["controls"] == 0, "read mode carries a control"
        assert seen["sections"] == ["Activiteit", "Intern", "Datums", "Onderdelen", "Organisatoren"]
        assert [c["title"] for c in seen["cards"]] == ["Wandeling", "Fietstocht"]
        assert all(c["card"] for c in seen["cards"]), "a component is not a card"
        assert all(c["badge"] == "0 ingeschreven" for c in seen["cards"])
        assert seen["cards"][0]["links"] == ["Externe info-URL: https://example.org/wandeling"]
        assert seen["cards"][1]["links"] == []
        assert seen["cards"][0]["products"] == [
            "Volwassene · € 5,00 · Betalend",
            "Kind · € 5,00 · Betalend",
        ]
        # 16 px between the cards; the heading row stands 8 px closer to its cards.
        gaps = seen["gaps"]
        assert gaps[0] == gaps[1] == gaps[3] == 16, f"the cards are not 16 px apart: {gaps}"
        assert seen["heading"][1] - seen["heading"][0] == 8, seen["heading"]
        shown, hidden = seen["organisers"]
        assert shown["state"] == "Contactpersoon" and hidden["state"] == "Geen contactpersoon"
        assert shown["facts"] == [f"feest-{TAG}@example.org", "0470 00 00 11"]
        assert hidden["facts"] == [f"jef-{TAG}@example.org", "niet getoond"]
        assert seen["page"][0] == seen["page"][1], "wider than the window"
        assert page.errors == []
    finally:
        page.close()


_EDIT = """() => { const all = s => [...document.querySelectorAll(s)];
  const mid = e => { const b = e.getBoundingClientRect(); return Math.round(b.top + b.height / 2); };
  const own = (row, s) => [...row.querySelectorAll(s)].find(e => e.closest('[data-group-row]') === row);
  const rows = s => all(s).map(row => ({
      handle: mid(own(row, '[data-row-handle]')), title: mid(own(row, '[data-row-title-line] h3, [data-row-title-line] [data-reference]')),
      menu: Math.round(own(row, '[data-row-menu-trigger]').getBoundingClientRect().left),
      aside: own(row, '[data-row-aside]') ? mid(own(row, '[data-row-aside]')) : null}));
  return {components: rows('#aa-group-components > [data-group-rows] > [data-group-row]'),
          products: rows('#aa-group-components [data-repeating-group^="p_order."] > [data-group-rows] > [data-group-row]'),
          organisers: rows('#aa-group-organisers > [data-group-rows] > [data-group-row]'),
          add: [Math.round(document.querySelector('#aa-group-components > [data-group-add-below]').getBoundingClientRect().top + scrollY),
                Math.round(all('#aa-group-components > [data-group-rows] > [data-group-row]').pop().getBoundingClientRect().bottom + scrollY)],
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize("width", [1440, 390])
def test_edit_mode_lines_up(setup, width):
    """The two positions that must line up (#1900): the handle and the title on
    one line in every card and row; the `⋯` of every row of a group on one x."""
    page = _page(setup, width, edit=True)
    try:
        seen = page.evaluate(_EDIT)
        print("MEASURE activity edit", width, seen)
        assert len(seen["components"]) == 2 and len(seen["products"]) == 4
        assert len(seen["organisers"]) == 2
        for group in ("components", "products", "organisers"):
            rows = seen[group]
            for row in rows:
                assert abs(row["handle"] - row["title"]) <= 2, (
                    f"{group}: the handle stands {row['handle'] - row['title']} px off its title"
                )
            assert len({row["menu"] for row in rows}) == 1, (
                f"{group}: the ⋯ of the rows stand on {sorted({row['menu'] for row in rows})}"
            )
        if width >= 1440:
            for row in seen["components"] + seen["organisers"]:
                assert abs(row["aside"] - row["title"]) <= 2, "the title line's slot left its line"
        assert seen["add"][0] >= seen["add"][1], '"+ Onderdeel" does not stand under the last card'
        assert seen["page"][0] == seen["page"][1], "wider than the window"
        assert page.errors == []
    finally:
        page.close()


def test_the_links_open_in_place_and_one_save_writes_them(setup):
    from app.domains.activities.api import ActivitySubRegistration

    _b, _session, made = setup
    first = made["components"][0]
    page = _page(setup, 1440, edit=True)
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        field = page.locator(f'[name="c.{first}.external_register_url"]')
        expect(field, "a closed line shows its fields").to_be_hidden()
        card = page.locator(f'#aa-group-components [data-row-key="{first}"]')
        expect(card.locator("[data-rare-line] summary").first).to_contain_text("1 ingevuld")
        card.locator("[data-rare-line] summary").first.click()
        expect(field).to_be_visible()
        field.fill("https://example.org/inschrijven")

        page.locator("#aa-group-components > [data-group-add-below] [data-group-add]").click()
        new = page.locator("#aa-group-components > [data-group-rows] > [data-group-row]").last
        new.locator('input[name$=".name"]').first.fill("Barbecue")
        new.locator("[data-rare-line] summary").first.click()
        new.locator('input[name$=".info_url"]').fill("https://example.org/barbecue")

        page.posts.clear()
        page.locator("[data-form-save]").first.click()
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        assert len(page.posts) == 1, f"{len(page.posts)} requests for one save: {page.posts}"
        assert page.errors == []
    finally:
        page.close()

    db = _db()
    try:
        stored = {
            c.name: (c.external_register_url, c.info_url)
            for c in db.query(ActivitySubRegistration).filter_by(activity_id=made["id"])
        }
    finally:
        db.close()
    assert stored["Wandeling"] == (
        "https://example.org/inschrijven",
        "https://example.org/wandeling",
    ), stored
    assert stored["Barbecue"] == (None, "https://example.org/barbecue"), stored


def test_a_switched_off_address_is_kept(setup):
    from app.domains.activities.api import organisers_for

    _b, _session, made = setup
    key = made["shown"]
    page = _page(setup, 1440, edit=True)
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        field = page.locator(f'[name="o.{key}.email_override"]')
        other = page.locator(f'[name="o.{key}.mobile_override"]')
        expect(field).to_have_value(f"feest-{TAG}@example.org")
        on = field.evaluate("e => getComputedStyle(e).backgroundColor")
        page.locator(f'label[for="o-{key}-show_email"]').click()
        state = field.evaluate(
            "e => ({readOnly: e.readOnly, disabled: e.disabled, background: getComputedStyle(e).backgroundColor,"
            " cursor: getComputedStyle(e).cursor, aria: e.getAttribute('aria-disabled')})"
        )
        print("MEASURE switched-off field", on, state)
        assert state["readOnly"], "the field beside a switch that is off can still be typed in"
        assert not state["disabled"], "the field is disabled: it would not be sent"
        assert state["background"] != on and state["cursor"] == "not-allowed", (
            f"the field does not look switched off: {state}"
        )
        assert state["aria"] == "true"
        assert not other.evaluate("e => e.readOnly"), "the mobile field went off with it"

        page.locator("[data-form-save]").first.click()
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        facts = page.locator(f'#aa-group-organisers [data-row-key="{key}"] [data-icon-fact]')
        expect(facts.first).to_have_text("niet getoond")
        assert page.errors == []
    finally:
        page.close()

    db = _db()
    try:
        row = next(o for o in organisers_for(db, made["id"]) if o.id == key)
        kept = (row.show_email, row.email_override)
    finally:
        db.close()
    assert kept == (False, f"feest-{TAG}@example.org"), (
        f"the stored other address did not survive the switch: {kept}"
    )

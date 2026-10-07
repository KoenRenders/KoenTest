"""E2E: an organiser's empty contact field shows the member's own value in grey (#1694).

In a real browser, because the three things that matter happen there: the grey
value is a placeholder and is NOT sent with the form, a member picked from the
search gets its own values into the row the page builds, and grey is a colour —
read from the rendered DOM, not from a class name.

Measured:

- an empty override shows the member's address and number as its placeholder,
  lighter than a typed value (the two computed colours differ);
- a save without typing leaves both overrides empty in the database;
- read mode shows the value that is used in the soft ink, marked "(van de
  fiche)", and a typed override in the normal ink;
- at 390 px the page does not scroll sideways and no placeholder is cut.

`E2E_SHOTS_1694` names a directory outside the repo for the screenshots.
"""

import os
import sys
from datetime import date

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

NAME = "Kwis met drie trekkers 1694"
PICKED = ("Pikbaar", "Zoekmaar")

_FIELDS = """() => {
  const group = document.getElementById('aa-group-organisers');
  const rows = [...group.querySelectorAll(':scope > [data-group-rows] > [data-group-row]')];
  const colour = (e, pseudo) => getComputedStyle(e, pseudo).color;
  return {
    page: [document.documentElement.scrollWidth, innerWidth],
    rows: rows.map(row => {
      const title = row.querySelector('[data-row-title-line] [data-reference], [data-row-title]');
      const field = name => {
        const box = [...row.querySelectorAll('[data-field]')].find(f => f.getAttribute('data-field').endsWith(name));
        const input = box.querySelector('input');
        if (input) {
          // The width the grey text needs, measured in the control's own font.
          const probe = document.createElement('span');
          probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font:' + getComputedStyle(input).font;
          probe.textContent = input.placeholder;
          document.body.appendChild(probe);
          const needed = probe.getBoundingClientRect().width;
          probe.remove();
          const style = getComputedStyle(input);
          const room = input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
          return {value: input.value, placeholder: input.placeholder, ink: colour(input), grey: colour(input, '::placeholder'),
                  fits: needed <= room + 0.5};
        }
        const shown = box.querySelector('[data-value]');
        const soft = shown.querySelector('[data-fallback]');
        return {text: shown.innerText.trim(), ink: colour(shown), soft: soft ? colour(soft) : null};
      };
      return {name: title ? title.innerText.trim() : '', email: field('.email_override'), mobile: field('.mobile_override')};
    }),
  };
}"""


def _seed() -> int:
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, add_organiser, update_organiser
    from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person

    db = SessionLocal()
    try:
        existing = db.query(Activity).filter(Activity.name == NAME).first()
        if existing is not None:
            return existing.id

        def member(first_name, last_name, email=None, mobile=None):
            person = Person(
                date_of_birth=date(1980, 1, 1),
                gender_code="M",
                first_name=first_name,
                last_name=last_name,
            )
            db.add(person)
            db.flush()
            household = Member()
            db.add(household)
            db.flush()
            db.add(
                MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID")
            )
            if email:
                db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=email))
            if mobile:
                db.add(ContactDetail(person_id=person.id, contact_type_code="MOBILE", value=mobile))
            db.flush()
            return person.id

        activity = Activity(name=NAME, location="Parochiezaal")
        db.add(activity)
        db.flush()
        both = add_organiser(
            db, activity.id, member("Beide", "Trekker", "beide.trekker@example.com", "0470000001")
        )
        neither = add_organiser(db, activity.id, member("Geen", "Trekker"))
        other = add_organiser(
            db, activity.id, member("Ander", "Trekker", "ander.trekker@example.com", "0470000002")
        )
        for row in (both, neither, other):
            update_organiser(db, activity.id, row.id, {"is_contact": True})
        update_organiser(
            db,
            activity.id,
            other.id,
            {"email_override": "quiz@example.com", "mobile_override": "0470000003"},
        )
        member(*PICKED, "pikbaar.zoekmaar@example.com", "0470000004")
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


def _page(setup, width: int, *, edit: bool):
    b, session, activity_id = setup
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 1000})
    login_met_sessie(page, session)
    page.goto(f"/admin/activiteiten/{activity_id}" + ("?bewerken=1" if edit else ""))
    pagina_klaar(page)
    return page


def _shot(page, name: str) -> None:
    out = os.environ.get("E2E_SHOTS_1694")
    if not out:
        return
    os.makedirs(out, exist_ok=True)
    page.locator("#aa-group-organisers").scroll_into_view_if_needed()
    page.screenshot(path=os.path.join(out, name))


def _overrides(activity_id: int) -> dict[str, tuple]:
    from app.database import SessionLocal
    from app.domains.activities.models import ActivityOrganiser
    from app.domains.mdm.api import Person

    db = SessionLocal()
    try:
        rows = db.query(ActivityOrganiser).filter_by(activity_id=activity_id).all()
        return {
            db.get(Person, row.person_id).first_name: (row.email_override, row.mobile_override)
            for row in rows
        }
    finally:
        db.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_an_empty_override_shows_the_members_value_in_grey(setup, width):
    page = _page(setup, width, edit=True)
    seen = page.evaluate(_FIELDS)
    rows = {row["name"]: row for row in seen["rows"]}
    both, neither, other = rows["Beide Trekker"], rows["Geen Trekker"], rows["Ander Trekker"]

    assert both["email"]["placeholder"] == "beide.trekker@example.com"
    assert both["mobile"]["placeholder"] == "0470 00 00 01"
    assert both["email"]["value"] == "" and both["mobile"]["value"] == ""
    assert neither["email"]["placeholder"] == "geen e-mailadres op de fiche"
    assert neither["mobile"]["placeholder"] == "geen nummer op de fiche"
    assert other["email"]["value"] == "quiz@example.com"

    # Grey is a colour: the placeholder is lighter than what is typed.
    for row in (both, neither, other):
        for field in (row["email"], row["mobile"]):
            assert field["grey"] != field["ink"], (
                f"the grey value has the ink of a typed one: {field}"
            )
            assert field["fits"], f"the grey value is cut off at {width} px: {field}"
    assert seen["page"][0] <= seen["page"][1], f"the page scrolls sideways: {seen['page']}"
    _shot(page, f"bewerken-{width}.png")
    page.close()


def test_a_save_without_typing_stores_no_override_and_a_picked_member_brings_its_own(setup):
    b, session, activity_id = setup
    page = _page(setup, 1440, edit=True)
    group = page.locator("#aa-group-organisers")
    group.locator('input[name="organiser_q"]').fill(PICKED[0])
    pick = group.locator("[data-group-pick]").first
    pick.wait_for()
    pick.click()
    added = page.evaluate(_FIELDS)["rows"][-1]
    assert added["name"] == " ".join(PICKED)
    assert added["email"]["placeholder"] == "pikbaar.zoekmaar@example.com"
    assert added["mobile"]["placeholder"] == "0470 00 00 04"
    assert added["email"]["value"] == "" and added["mobile"]["value"] == ""
    _shot(page, "bewerken-1440-na-kiezen.png")

    page.click("[data-action-bar] [data-form-save]")
    page.wait_for_selector('[data-form-flow][data-mode="read"]')
    pagina_klaar(page)
    stored = _overrides(activity_id)
    assert stored["Beide"] == (None, None), "the grey value was sent as a value"
    assert stored["Geen"] == (None, None)
    assert stored[PICKED[0]] == (None, None), "the picked member's grey value was sent"
    assert stored["Ander"] == ("quiz@example.com", "0470000003")
    page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_read_mode_shows_the_used_value_soft_and_marked(setup, width):
    page = _page(setup, width, edit=False)
    seen = page.evaluate(_FIELDS)
    rows = {row["name"]: row for row in seen["rows"]}
    both, neither, other = rows["Beide Trekker"], rows["Geen Trekker"], rows["Ander Trekker"]
    assert both["email"]["text"] == "beide.trekker@example.com (van de fiche)"
    assert both["mobile"]["text"] == "0470 00 00 01 (van de fiche)"
    assert neither["email"]["text"] == "geen e-mailadres op de fiche"
    assert neither["mobile"]["text"] == "geen nummer op de fiche"
    assert other["mobile"]["text"] == "0470 00 00 03" and other["mobile"]["soft"] is None
    assert both["mobile"]["soft"] and both["mobile"]["soft"] != other["mobile"]["ink"], (
        "the member's value reads as loud as a typed override"
    )
    assert seen["page"][0] <= seen["page"][1], f"the page scrolls sideways: {seen['page']}"
    _shot(page, f"lezen-{width}.png")
    page.close()

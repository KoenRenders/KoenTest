"""The one save of a household does what the portal's row routes did (#1590).

`mdm.household_save.save_household` writes the persons, their e-mail addresses
and the address in one transaction. This file is the proof the merge asks for,
rule by rule: every refusal a portal route (or the service behind it) made is
made here, every history row it wrote is written here, and a refusal anywhere
leaves nothing behind.

New with #1590, and marked NEW at their test:

- every refusal of one save comes back at once, each at its place;
- a row that did not change is not written and gets no history row;
- the e-mail history of a member's own save says `member_self`;
- one transaction — saving a person used to be two (the person, then the e-mail
  rows), so a refusal in the second left the first stored.

What is a choice for Koen (the main member's removal, the relation of a new
person, the primary address, creating an address) keeps today's behaviour, and
that is proven here as what holds today.

Each rule was broken once to see its test red; what was broken stands in the
test's docstring.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.mdm.household_save import (
    AddressRow,
    EmailRow,
    HouseholdSave,
    HouseholdSaveRefused,
    PersonRow,
    save_household,
)
from app.domains.mdm.models import (
    Address,
    AddressHistory,
    ContactDetail,
    ContactDetailHistory,
    Member,
    MemberPerson,
    MemberPersonHistory,
    Person,
    PersonHistory,
    PostalCode,
    RelationType,
)
from app.kernel.refusals import FieldError

ACTOR = "an@example.com"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _household(db) -> dict:
    """An (main member, with an address and two e-mail addresses), Bert (partner)
    and Cas (child)."""
    for code, town in (("2400", "Mol"), ("2440", "Geel")):
        if db.query(PostalCode).filter(PostalCode.postal_code == code).first() is None:
            db.add(PostalCode(postal_code=code, municipality=town))
    db.flush()
    household = Member()
    db.add(household)
    db.flush()
    people = {}
    for name, relation, born in (
        ("An", "HOOFDLID", date(1980, 1, 1)),
        ("Bert", "PARTNER", date(1981, 2, 2)),
        ("Cas", "KIND", date(2010, 3, 3)),
    ):
        person = Person(first_name=name, last_name="Voorbeeld", date_of_birth=born, gender_code="M")
        db.add(person)
        db.flush()
        db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type=relation))
        people[name] = person
    an = people["An"]
    postal = db.query(PostalCode).filter(PostalCode.postal_code == "2400").one()
    db.add(
        Address(person_id=an.id, street="Dorpsstraat", house_number="1", postal_code_id=postal.id)
    )
    db.add(ContactDetail(person_id=an.id, contact_type_code="EMAIL", value=ACTOR, is_primary=True))
    db.add(ContactDetail(person_id=an.id, contact_type_code="EMAIL", value="an.werk@example.com"))
    db.add(
        ContactDetail(
            person_id=an.id, contact_type_code="MOBILE", value="0470000000", is_primary=True
        )
    )
    db.commit()
    return {"household": household, **people}


def _as_is(db, household: Member) -> HouseholdSave:
    """The household as the form sends it when nothing was touched."""
    db.expire_all()
    rows = []
    links = sorted(
        (m for m in household.member_persons if m.deleted_at is None), key=lambda m: m.person_id
    )
    address = None
    for link in links:
        p = link.person
        contacts = {
            c.contact_type_code: c.value
            for c in p.contact_details
            if c.contact_type_code != "EMAIL"
        }
        rows.append(
            PersonRow(
                key=str(p.id),
                first_name=p.first_name,
                last_name=p.last_name,
                date_of_birth=p.date_of_birth,
                gender_code=p.gender_code,
                phone=contacts.get("PHONE", ""),
                mobile=contacts.get("MOBILE", ""),
                emails=[
                    EmailRow(str(c.id), c.value, primary=c.is_primary)
                    for c in sorted(p.contact_details, key=lambda c: c.id)
                    if c.contact_type_code == "EMAIL"
                ],
            )
        )
        if p.address is not None:
            a = p.address
            address = AddressRow(
                a.street, a.house_number, a.bus_number or "", a.postal_code.postal_code
            )
    return HouseholdSave(persons=rows, address=address)


def _row(payload: HouseholdSave, person: Person) -> PersonRow:
    return next(r for r in payload.persons if r.key == str(person.id))


def _save(db, world, payload: HouseholdSave, by: str = "An"):
    return save_household(db, world["household"], payload, by=world[by], actor=ACTOR)


def _places(db, world, payload: HouseholdSave, by: str = "An") -> dict[str, str]:
    with pytest.raises(HouseholdSaveRefused) as refusal:
        _save(db, world, payload, by)
    places = [e.field for e in refusal.value.errors]
    assert len(places) == len(set(places)), f"a place named twice: {places}"
    return {e.field: e.message for e in refusal.value.errors}


def _counts(db) -> dict[str, int]:
    """Everything a save can write, counted — to prove "nothing written"."""
    db.expire_all()
    models = (
        Person,
        MemberPerson,
        ContactDetail,
        Address,
        PersonHistory,
        MemberPersonHistory,
        ContactDetailHistory,
        AddressHistory,
    )
    return {m.__name__: db.query(m).execution_options(include_deleted=True).count() for m in models}


def _history(db, model, **where) -> list[tuple[str, str, str]]:
    rows = db.query(model).filter_by(**where).order_by(model.id).all()
    return [(r.operation, r.action, r.source) for r in rows]


# ── A save that changes nothing writes nothing ───────────────────────────────


def test_new_an_untouched_household_writes_no_row_and_no_history(db_session):
    """NEW: a save of the whole household would otherwise log an update for every
    person at every save. Proven red by writing the address whenever the form
    carries it (as the row route did for `bus_number`): an `address_updated` row
    appears for a household nobody changed."""
    world = _household(db_session)
    before = _counts(db_session)
    _save(db_session, world, _as_is(db_session, world["household"]))
    assert _counts(db_session) == before


# ── What the row routes did ──────────────────────────────────────────────────


def test_a_person_is_changed_with_one_history_row(db_session):
    """`update_household_person`: name, birth date, gender — `person_updated`,
    source `member_self`, and only what changed."""
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    row = _row(payload, world["Cas"])
    row.first_name, row.date_of_birth = "Casper", date(2011, 4, 4)
    _save(db_session, world, payload)
    db_session.expire_all()
    cas = db_session.get(Person, world["Cas"].id)
    assert (cas.first_name, cas.date_of_birth) == ("Casper", date(2011, 4, 4))
    assert _history(db_session, PersonHistory, person_id=cas.id) == [
        ("update", "person_updated", "member_self")
    ]
    assert _history(db_session, PersonHistory, person_id=world["Bert"].id) == [], (
        "the others are not written"
    )


def _contacts(db, person: Person) -> dict[str, str]:
    db.expire_all()
    return {
        c.contact_type_code: c.value
        for c in db.get(Person, person.id).contact_details
        if c.contact_type_code != "EMAIL"
    }


def test_phone_and_mobile_are_set_changed_and_removed(db_session):
    """`_upsert_contact`: a value sets or changes the row, an empty one removes
    it; each with `contacts_updated`. On Bert, the partner: the main member's
    mobile cannot be removed here (the tests of that rule are below)."""
    world = _household(db_session)
    bert = world["Bert"]
    payload = _as_is(db_session, world["household"])
    _row(payload, bert).phone, _row(payload, bert).mobile = "014 00 00 00", "0471 00 00 00"
    _save(db_session, world, payload)
    assert _contacts(db_session, bert) == {"PHONE": "014 00 00 00", "MOBILE": "0471 00 00 00"}
    phone = next(c for c in bert.contact_details if c.contact_type_code == "PHONE")
    assert phone.is_primary

    payload = _as_is(db_session, world["household"])
    _row(payload, bert).phone, _row(payload, bert).mobile = "014 11 11 11", ""
    _save(db_session, world, payload)
    assert _contacts(db_session, bert) == {"PHONE": "014 11 11 11"}

    payload = _as_is(db_session, world["household"])
    _row(payload, bert).phone = ""
    _save(db_session, world, payload)
    assert _contacts(db_session, bert) == {}
    actions = [h[:2] for h in _history(db_session, ContactDetailHistory, person_id=bert.id)]
    assert actions[:2] == [("insert", "contacts_updated")] * 2
    assert all(action == "contacts_updated" for _operation, action in actions)
    assert len(actions) == 5, "set twice, changed once, removed twice"


# ── The main member can be called (#1590) ────────────────────────────────────

MOBILE_REQUIRED = "Mobiel nummer is verplicht voor het hoofdgezinslid."


def test_new_the_main_members_mobile_cannot_be_emptied(db_session):
    """NEW with #1590: `MemberPerson.require_main_member_mobile`, the rule Word
    lid asks, at this door too — at the Gsm field, with nothing written, the
    good change in the same row neither."""
    world = _household(db_session)
    an = world["An"]
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    _row(payload, an).mobile = "   "
    _row(payload, an).phone = "014 00 00 00"
    assert _places(db_session, world, payload) == {f"h.{an.id}.mobile": MOBILE_REQUIRED}
    assert _counts(db_session) == before
    assert _contacts(db_session, an) == {"MOBILE": "0470000000"}


def test_new_a_main_member_who_never_had_a_mobile_is_asked_one(db_session):
    """An old household: the number was never there, and the form sends none.
    The rule looks at what the form says, not at what changed — and the same
    form with a number is saved, so the missing number is the cause."""
    world = _household(db_session)
    an = world["An"]
    for contact in list(an.contact_details):
        if contact.contact_type_code == "MOBILE":
            db_session.delete(contact)
    db_session.commit()
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    assert _row(payload, an).mobile == "", "this world must start without the number"
    assert _places(db_session, world, payload) == {f"h.{an.id}.mobile": MOBILE_REQUIRED}
    assert _counts(db_session) == before

    payload = _as_is(db_session, world["household"])
    _row(payload, an).mobile = "0470 11 22 33"
    _save(db_session, world, payload)
    assert _contacts(db_session, an) == {"MOBILE": "0470 11 22 33"}


def test_a_partner_and_a_child_need_no_mobile(db_session):
    """The other half: the rule is the main member's. Bert and Cas have no
    number and send none, a new person neither — and the save goes through,
    which the changed name shows."""
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    assert (_row(payload, world["Bert"]).mobile, _row(payload, world["Cas"]).mobile) == ("", "")
    _row(payload, world["Cas"]).first_name = "Casper"
    payload.persons.append(
        PersonRow(
            key="n1",
            first_name="Dien",
            last_name="Voorbeeld",
            date_of_birth=date(2015, 5, 5),
            gender_code="F",
        )
    )
    _save(db_session, world, payload)
    db_session.expire_all()
    assert db_session.get(Person, world["Cas"].id).first_name == "Casper"
    assert db_session.query(Person).filter_by(first_name="Dien").one()


def test_the_mobile_refusal_comes_with_the_other_refusals_of_the_save(db_session):
    """One answer for the whole form: the main member's mobile beside another
    person's blank name and the address."""
    world = _household(db_session)
    an, bert = world["An"], world["Bert"]
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    _row(payload, an).mobile = ""
    _row(payload, bert).last_name = ""
    payload.address.postal_code = "9999"
    places = _places(db_session, world, payload)
    assert set(places) == {f"h.{an.id}.mobile", f"h.{bert.id}.last_name", "address.postal_code"}
    assert places[f"h.{an.id}.mobile"] == MOBILE_REQUIRED
    assert _counts(db_session) == before


def test_a_person_is_added_as_a_child_with_its_history(db_session):
    """`add_household_person`: today a member's new person is always a child, and
    gets no address. `person_created` and `person_added_to_family`."""
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    payload.persons.append(
        PersonRow(
            key="n1",
            first_name="Dien",
            last_name="Voorbeeld",
            date_of_birth=date(2015, 5, 5),
            gender_code="F",
            emails=[EmailRow("n2", "dien@example.com")],
        )
    )
    _save(db_session, world, payload)
    db_session.expire_all()
    dien = db_session.query(Person).filter(Person.first_name == "Dien").one()
    link = db_session.query(MemberPerson).filter_by(person_id=dien.id).one()
    assert (
        link.member_id == world["household"].id and link.relation_type == RelationType.ADULT_CHILD
    )
    assert dien.address is None
    mail = next(c for c in dien.contact_details if c.contact_type_code == "EMAIL")
    assert mail.value == "dien@example.com" and mail.is_primary, (
        "the first address is the primary one"
    )
    assert _history(db_session, PersonHistory, person_id=dien.id) == [
        ("insert", "person_created", "member_self")
    ]
    assert _history(db_session, MemberPersonHistory, person_id=dien.id) == [
        ("insert", "person_added_to_family", "member_self")
    ]


def test_a_person_the_form_no_longer_has_leaves_the_household(db_session):
    """`remove_household_person`: the LINK is soft-deleted with
    `person_removed_from_family`; the person and their rows stay."""
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    payload.persons = [r for r in payload.persons if r.key != str(world["Cas"].id)]
    _save(db_session, world, payload)
    db_session.expire_all()
    link = (
        db_session.query(MemberPerson)
        .execution_options(include_deleted=True)
        .filter_by(person_id=world["Cas"].id)
        .one()
    )
    assert link.deleted_at is not None
    assert db_session.get(Person, world["Cas"].id) is not None, "the person stays"
    assert _history(db_session, MemberPersonHistory, person_id=world["Cas"].id) == [
        ("delete", "person_removed_from_family", "member_self")
    ]


def test_nobody_removes_themselves(db_session):
    """ "Je kan jezelf niet uit het gezin verwijderen." — named as that row, so the
    screen can put it back. Proven red by dropping the check from
    `detach_household_person`: Bert takes himself out."""
    world = _household(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    payload.persons = [r for r in payload.persons if r.key != str(world["Bert"].id)]
    assert _places(db_session, world, payload, by="Bert") == {
        f"h.{world['Bert'].id}": "Je kan jezelf niet uit het gezin verwijderen."
    }
    assert _counts(db_session) == before


def test_today_the_main_member_can_be_taken_out_by_another_member(db_session):
    """What holds TODAY, kept until Koen decides: the only refusal is "not
    yourself", so a partner can remove the main member."""
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    payload.persons = [r for r in payload.persons if r.key != str(world["An"].id)]
    _save(db_session, world, payload, by="Bert")
    db_session.expire_all()
    live = db_session.query(MemberPerson).filter_by(member_id=world["household"].id).all()
    assert world["An"].id not in {m.person_id for m in live}


def test_birth_date_and_gender_are_required_and_named_at_their_field(db_session):
    """#681, the household link's own rule — at the field that is missing."""
    world = _household(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    _row(payload, world["Cas"]).gender_code = None
    payload.persons.append(PersonRow(key="n1", first_name="Dien", last_name="Voorbeeld"))
    message = "Geboortedatum en geslacht zijn verplicht voor elk gezinslid."
    assert _places(db_session, world, payload) == {
        f"h.{world['Cas'].id}.gender_code": message,
        "h.n1.date_of_birth": message,
    }
    assert _counts(db_session) == before


def test_a_blank_name_is_refused_at_its_field(db_session):
    world = _household(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    _row(payload, world["Cas"]).first_name = "  "
    payload.persons.append(
        PersonRow(
            key="n1",
            first_name="Dien",
            last_name="",
            date_of_birth=date(2015, 5, 5),
            gender_code="F",
        )
    )
    message = "Voornaam en achternaam zijn verplicht."
    assert _places(db_session, world, payload) == {
        f"h.{world['Cas'].id}.first_name": message,
        "h.n1.last_name": message,
    }
    assert _counts(db_session) == before


def test_a_person_of_another_household_is_not_touched(db_session):
    """The household boundary: a key that is another household's person is not
    this household's row."""
    world = _household(db_session)
    other = Person(
        first_name="Vreemd", last_name="Elders", date_of_birth=date(1970, 1, 1), gender_code="M"
    )
    db_session.add(other)
    db_session.commit()
    payload = _as_is(db_session, world["household"])
    payload.persons.append(
        PersonRow(
            key=str(other.id),
            first_name="Gekaapt",
            last_name="Elders",
            date_of_birth=date(1970, 1, 1),
            gender_code="M",
        )
    )
    assert list(_places(db_session, world, payload)) == [f"h.{other.id}"]
    db_session.expire_all()
    assert db_session.get(Person, other.id).first_name == "Vreemd"


# ── E-mail addresses ─────────────────────────────────────────────────────────


def test_email_rows_are_edited_added_and_removed_with_the_members_own_source(db_session):
    """`apply_email_rows`: changed text follows, a new row is added (not primary
    while one exists), a row the form no longer has goes. NEW: the history says
    `member_self` — the row functions wrote `admin_update` for the member too."""
    world = _household(db_session)
    an = world["An"]
    payload = _as_is(db_session, world["household"])
    row = _row(payload, an)
    primary, work = row.emails
    work.value = "an.kantoor@example.com"
    row.emails.append(EmailRow("n1", "an.extra@example.com"))
    bert = _row(payload, world["Bert"])
    bert.emails.append(EmailRow("n2", "bert@example.com"))
    _save(db_session, world, payload)
    db_session.expire_all()
    mails = {
        c.value: c.is_primary
        for c in db_session.get(Person, an.id).contact_details
        if c.contact_type_code == "EMAIL"
    }
    assert mails == {ACTOR: True, "an.kantoor@example.com": False, "an.extra@example.com": False}
    history = _history(db_session, ContactDetailHistory, person_id=an.id)
    assert history == [
        ("update", "email_edited", "member_self"),
        ("insert", "email_added", "member_self"),
    ]
    assert _history(db_session, ContactDetailHistory, person_id=world["Bert"].id) == [
        ("insert", "email_promoted", "member_self")
    ], "a person's first address becomes the primary one"

    payload = _as_is(db_session, world["household"])
    row = _row(payload, an)
    row.emails = [e for e in row.emails if e.value != "an.extra@example.com"]
    _save(db_session, world, payload)
    db_session.expire_all()
    left = {
        c.value
        for c in db_session.get(Person, an.id).contact_details
        if c.contact_type_code == "EMAIL"
    }
    assert left == {ACTOR, "an.kantoor@example.com"}


def test_the_same_address_twice_is_stored_once_and_an_empty_row_is_nothing(db_session):
    world = _household(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    row = _row(payload, world["An"])
    row.emails += [EmailRow("n1", ACTOR.upper()), EmailRow("n2", "  ")]
    _save(db_session, world, payload)
    assert _counts(db_session) == before


def test_the_primary_mark_moves_when_the_form_marks_another_row(db_session):
    """`make_email_primary`: the old one is put back first (one primary per
    person in the database), `email_demoted` then `email_promoted`."""
    world = _household(db_session)
    an = world["An"]
    payload = _as_is(db_session, world["household"])
    primary, work = _row(payload, an).emails
    primary.primary, work.primary = False, True
    _save(db_session, world, payload)
    db_session.expire_all()
    mails = {
        c.value: c.is_primary
        for c in db_session.get(Person, an.id).contact_details
        if c.contact_type_code == "EMAIL"
    }
    assert mails == {ACTOR: False, "an.werk@example.com": True}
    assert [h[1] for h in _history(db_session, ContactDetailHistory, person_id=an.id)] == [
        "email_demoted",
        "email_promoted",
    ]


def test_today_the_primary_and_the_last_address_may_go(db_session):
    """What holds TODAY (Koen, 27 September 2026: "niets aanwijzen, niets
    weigeren"), kept until he decides otherwise: the primary address may be
    removed, nothing is promoted in its place, and the last one may go too."""
    world = _household(db_session)
    an = world["An"]
    payload = _as_is(db_session, world["household"])
    row = _row(payload, an)
    row.emails = [e for e in row.emails if not e.primary]
    _save(db_session, world, payload)
    db_session.expire_all()
    mails = {
        c.value: c.is_primary
        for c in db_session.get(Person, an.id).contact_details
        if c.contact_type_code == "EMAIL"
    }
    assert mails == {"an.werk@example.com": False}, "zero primary addresses is a valid state"

    payload = _as_is(db_session, world["household"])
    _row(payload, an).emails = []
    _save(db_session, world, payload)
    db_session.expire_all()
    assert [
        c for c in db_session.get(Person, an.id).contact_details if c.contact_type_code == "EMAIL"
    ] == []


# ── The address ──────────────────────────────────────────────────────────────


def test_the_address_is_changed_with_one_history_row_and_only_when_it_differs(db_session):
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    payload.address.street, payload.address.bus_number, payload.address.postal_code = (
        "Kerkstraat",
        "B",
        "2440",
    )
    _save(db_session, world, payload)
    db_session.expire_all()
    address = db_session.get(Person, world["An"].id).address
    assert (address.street, address.house_number, address.bus_number) == ("Kerkstraat", "1", "B")
    assert address.postal_code.postal_code == "2440"
    assert _history(db_session, AddressHistory, address_id=address.id) == [
        ("update", "address_updated", "member_self")
    ]


def test_an_unknown_postal_code_is_refused_at_its_field(db_session):
    """ "Onbekende postcode: 9999" — and the person change in the same save is not
    stored either."""
    world = _household(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    payload.address.postal_code = "9999"
    _row(payload, world["Cas"]).first_name = "Niet bewaard"
    assert _places(db_session, world, payload) == {
        "address.postal_code": "Onbekende postcode: 9999"
    }
    assert _counts(db_session) == before
    db_session.expire_all()
    assert db_session.get(Person, world["Cas"].id).first_name == "Cas"


def test_today_a_household_without_an_address_gets_none_from_the_portal(db_session):
    """What holds TODAY, kept until Koen decides: the portal changes an address
    that exists and creates none."""
    world = _household(db_session)
    db_session.delete(db_session.get(Person, world["An"].id).address)
    db_session.commit()
    payload = _as_is(db_session, world["household"])
    payload.address = AddressRow("Kerkstraat", "5", "", "2440")
    _save(db_session, world, payload)
    db_session.expire_all()
    assert db_session.get(Person, world["An"].id).address is None


# ── One transaction, every refusal at once ───────────────────────────────────


def test_new_every_refusal_comes_back_at_once_and_nothing_is_written(db_session):
    """NEW: one transaction and all refusals together. Until #1590 the person was
    committed before the e-mail rows were looked at. Proven red by committing the
    savepoint on a refusal: Casper is stored while the save says "refused"."""
    world = _household(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    _row(payload, world["Cas"]).first_name = "Casper"
    _row(payload, world["Bert"]).last_name = ""
    payload.persons.append(PersonRow(key="n1", first_name="Dien", last_name="Voorbeeld"))
    payload.address.postal_code = "9999"
    payload.errors = [FieldError(f"h.{world['An'].id}.date_of_birth", "Ongeldige geboortedatum.")]
    places = _places(db_session, world, payload)
    assert set(places) == {
        f"h.{world['An'].id}.date_of_birth",
        f"h.{world['Bert'].id}.last_name",
        "h.n1.date_of_birth",
        "address.postal_code",
    }
    assert _counts(db_session) == before
    db_session.expire_all()
    assert db_session.get(Person, world["Cas"].id).first_name == "Cas", (
        "the good row is not written either"
    )

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

Koen's rules of 5 October 2026 (#1603) are proven here where #1590 pinned
"today": the main member stays, a person added is a partner or a child (the
member's choice, the one rule's default), the primary address may go and nothing
takes its place, an address can be created and is whole or not there, and the
main member's mobile number is not asked at this door.

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
    """A person's own fields: name, birth date, gender — `person_updated`,
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


def test_the_main_members_mobile_is_not_asked_here(db_session):
    """Koen, 5 October 2026 (#1603): on Mijn gezin the main member's mobile number
    is not required. With one save for the whole household the requirement
    blocked every change of a household whose main member has none (10 of 116 on
    PROD). Word lid still asks it (`membership/tests/test_signup_form.py`).

    Both halves: the number can be emptied, and a main member who never had one
    saves something else. Proven red by asking
    `MemberPerson.require_main_member_mobile` in `_save_person` again: both
    saves are refused at the Gsm field.
    """
    world = _household(db_session)
    an = world["An"]
    payload = _as_is(db_session, world["household"])
    _row(payload, an).mobile = "   "
    _row(payload, an).phone = "014 00 00 00"
    _save(db_session, world, payload)
    assert _contacts(db_session, an) == {"PHONE": "014 00 00 00"}

    payload = _as_is(db_session, world["household"])
    assert _row(payload, an).mobile == "", "this world must be without the number now"
    _row(payload, world["Cas"]).first_name = "Casper"
    _save(db_session, world, payload)
    db_session.expire_all()
    assert db_session.get(Person, world["Cas"].id).first_name == "Casper"


# ── The relation of a person a member adds (#1603) ───────────────────────────


def _new_person(key: str, first_name: str, relation_type: str = "") -> PersonRow:
    return PersonRow(
        key=key,
        first_name=first_name,
        last_name="Voorbeeld",
        date_of_birth=date(2015, 5, 5),
        gender_code="F",
        relation_type=relation_type,
    )


def _relation_of(db, first_name: str) -> RelationType:
    person = db.query(Person).filter(Person.first_name == first_name).one()
    return db.query(MemberPerson).filter_by(person_id=person.id).one().relation_type


def test_a_person_is_added_with_its_history_and_a_child_where_there_is_a_partner(db_session):
    """`person_created` and `person_added_to_family`, no address. The household
    has a partner (Bert), so the one rule's default for the new person is a child."""
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    row = _new_person("n1", "Dien")
    row.emails = [EmailRow("n2", "dien@example.com")]
    payload.persons.append(row)
    _save(db_session, world, payload)
    db_session.expire_all()
    dien = db_session.query(Person).filter(Person.first_name == "Dien").one()
    link = db_session.query(MemberPerson).filter_by(person_id=dien.id).one()
    assert (
        link.member_id == world["household"].id and link.relation_type == RelationType.ADULT_CHILD
    )
    assert dien.address is None
    mail = next(c for c in dien.contact_details if c.contact_type_code == "EMAIL")
    # CR-22 R15 (#1711): an address typed in Mijn gezin waits for its code,
    # and a waiting address is never the primary one. It was primary at once.
    assert mail.value == "dien@example.com" and not mail.is_primary
    assert mail.confirmed_at is None, "an address the member typed counted without its code"
    assert _history(db_session, PersonHistory, person_id=dien.id) == [
        ("insert", "person_created", "member_self")
    ]
    assert _history(db_session, MemberPersonHistory, person_id=dien.id) == [
        ("insert", "person_added_to_family", "member_self")
    ]


def test_without_a_partner_the_first_added_person_is_one_and_the_next_a_child(db_session):
    """The one rule (`default_relation`) for a person the member chose nothing for:
    a partner while the household has none, a child after that — also for two
    persons added in the SAME save. Until #1603 everyone added here was a child.

    Proven red by making `insert_household_person` always link a child (the old
    behaviour): "Eva" is a child; and by not handing the new link to the
    household: both are partners.
    """
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    payload.persons = [r for r in payload.persons if r.key != str(world["Bert"].id)]
    payload.persons += [_new_person("n1", "Eva"), _new_person("n2", "Fien")]
    _save(db_session, world, payload)
    db_session.expire_all()
    assert _relation_of(db_session, "Eva") == RelationType.PARTNER
    assert _relation_of(db_session, "Fien") == RelationType.ADULT_CHILD


def test_the_member_chooses_partner_or_child(db_session):
    """What the member chose wins from the default, both ways: a child where the
    default is a partner, and a second partner where the default is a child
    (nothing refuses a second partner — Koen, 29 September 2026)."""
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    payload.persons.append(_new_person("n1", "Gust", relation_type="PARTNER"))
    _save(db_session, world, payload)
    db_session.expire_all()
    assert _relation_of(db_session, "Gust") == RelationType.PARTNER

    other = _household(db_session)
    payload = _as_is(db_session, other["household"])
    payload.persons = [r for r in payload.persons if r.key != str(other["Bert"].id)]
    payload.persons.append(_new_person("n1", "Hanne", relation_type="KIND"))
    _save(db_session, other, payload)
    db_session.expire_all()
    assert _relation_of(db_session, "Hanne") == RelationType.ADULT_CHILD


@pytest.mark.parametrize("asked", ["HOOFDLID", "BUUR"])
def test_never_a_second_main_member_and_nothing_outside_the_list(db_session, asked):
    """ "Kies partner of kind." at the relation field, with nothing written.
    Proven red by accepting whatever is asked: a household with two main members."""
    world = _household(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    payload.persons.append(_new_person("n1", "Ilse", relation_type=asked))
    assert _places(db_session, world, payload) == {"h.n1.relation_type": "Kies partner of kind."}
    assert _counts(db_session) == before


def test_the_relation_of_a_person_who_is_there_is_not_read(db_session):
    """Whether an existing person's kind can be changed stays as it was: it
    cannot. A form that sends one for Cas changes nothing."""
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    _row(payload, world["Cas"]).relation_type = "PARTNER"
    _save(db_session, world, payload)
    db_session.expire_all()
    link = db_session.query(MemberPerson).filter_by(person_id=world["Cas"].id).one()
    assert link.relation_type == RelationType.ADULT_CHILD


def test_a_person_the_form_no_longer_has_leaves_the_household(db_session):
    """A removal: the LINK is soft-deleted with
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


def test_the_main_member_stays_whoever_asks(db_session):
    """Koen, 5 October 2026 (#1603): the main member cannot be removed — "Een
    gezin heeft een hoofdlid nodig.", named as that row, with nothing written and
    the other change of the same save not stored either. Until then the only
    refusal was "not yourself", so a partner could take the main member out.

    Proven red by dropping the check from `detach_household_person`: An's link is
    soft-deleted.
    """
    world = _household(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    payload.persons = [r for r in payload.persons if r.key != str(world["An"].id)]
    _row(payload, world["Cas"]).first_name = "Niet bewaard"
    assert _places(db_session, world, payload, by="Bert") == {
        f"h.{world['An'].id}": "Een gezin heeft een hoofdlid nodig."
    }
    assert _counts(db_session) == before
    db_session.expire_all()
    live = db_session.query(MemberPerson).filter_by(member_id=world["household"].id).all()
    assert world["An"].id in {m.person_id for m in live}
    assert db_session.get(Person, world["Cas"].id).first_name == "Cas"


def test_the_main_member_removing_themselves_hears_that_first(db_session):
    """Removing yourself stays refused as it was, in its own words — also for the
    main member, for whom both rules hold."""
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    payload.persons = [r for r in payload.persons if r.key != str(world["An"].id)]
    assert _places(db_session, world, payload, by="An") == {
        f"h.{world['An'].id}": "Je kan jezelf niet uit het gezin verwijderen."
    }


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
    """A new row is added (never primary: it waits), a row the form no longer
    has goes, and the history says `member_self`.

    Since CR-22 R15 (#1711) changed text does NOT follow: the address that
    counts stays as it is and the new one waits beside it — this test expected
    `an.werk` to become `an.kantoor` in place, with `email_edited`."""
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
    assert mails == {
        ACTOR: True,
        "an.werk@example.com": False,
        "an.kantoor@example.com": False,
        "an.extra@example.com": False,
    }
    history = _history(db_session, ContactDetailHistory, person_id=an.id)
    assert history == [
        ("insert", "email_added", "member_self"),
        ("insert", "email_added", "member_self"),
    ]
    assert _history(db_session, ContactDetailHistory, person_id=world["Bert"].id) == [
        ("insert", "email_added", "member_self")
    ], "a person's first address waits too: it is not the primary one before its code"

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
    assert left == {ACTOR, "an.werk@example.com", "an.kantoor@example.com"}


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


def test_the_primary_and_the_last_address_may_go(db_session):
    """Koen, 27 September 2026 ("niets aanwijzen, niets weigeren"), confirmed on
    5 October 2026 (#1603, rule 3): the primary address may be removed, nothing
    is promoted in its place, and the last one may go too."""
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


def test_the_primary_address_removed_and_another_added_in_one_save(db_session):
    """Found by a browser test of the one save (#1603), and a 500 until then: the
    row routes could do only one of the two at a time. The unit of work inserted
    the new row — primary, because the person had no primary address left —
    before it deleted the old one, and `uq_contact_details_one_primary_per_type`
    refused. The removals are flushed first now.

    Through the member's own save the new address waits (CR-22 R15, #1711)
    and is not the primary one before its code: the person has none meanwhile.
    The address that stays is not touched.
    """
    world = _household(db_session)
    an = world["An"]
    payload = _as_is(db_session, world["household"])
    row = _row(payload, an)
    row.emails = [e for e in row.emails if not e.primary] + [EmailRow("n1", "an.nieuw@example.com")]
    _save(db_session, world, payload)
    db_session.expire_all()
    mails = {
        c.value: c.is_primary
        for c in db_session.get(Person, an.id).contact_details
        if c.contact_type_code == "EMAIL"
    }
    assert mails == {"an.werk@example.com": False, "an.nieuw@example.com": False}


def test_the_board_removes_the_primary_address_and_adds_another_in_one_write(db_session):
    """The board's write counts at once, so its new row IS the primary one when
    the person has none left — and the removal must reach the database first.

    Until #1711 the test above showed this through the member's save, proven
    red by taking the flush out of `write_email_rows`. That proof no longer
    turns red (tried on 8 October 2026): since #1704 the address rule queries
    before a row is made, and that query flushes the removal by itself. The
    flush stays as it is; this test holds the outcome.
    """
    from app.domains.mdm.service import write_email_rows

    world = _household(db_session)
    an = world["An"]
    rows = {c.id: c for c in an.contact_details if c.contact_type_code == "EMAIL"}
    texts = {row_id: ("" if c.is_primary else c.value) for row_id, c in rows.items()}
    write_email_rows(db_session, an, texts, ["an.nieuw@example.com"], actor="bestuur@example.com")
    db_session.commit()
    db_session.expire_all()
    mails = {
        c.value: (c.is_primary, c.confirmed_at is not None)
        for c in db_session.get(Person, an.id).contact_details
        if c.contact_type_code == "EMAIL"
    }
    assert mails == {
        "an.werk@example.com": (False, True),
        "an.nieuw@example.com": (True, True),
    }


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


WHOLE_ADDRESS = "Een adres heeft een straat, een huisnummer en een postcode nodig."


def _without_address(db) -> dict:
    world = _household(db)
    db.delete(db.get(Person, world["An"].id).address)
    db.commit()
    return world


def test_a_household_without_an_address_gets_one_on_its_main_member(db_session):
    """Koen, 5 October 2026 (#1603): the address can be created from Mijn gezin.
    It hangs on the main member, as at sign-up, with `address_created` — also
    when another member of the household saves. Until then the portal changed an
    address that existed and created none.

    Proven red by returning from `_save_address` when the household has no
    address (the old behaviour): no address after the save.
    """
    world = _without_address(db_session)
    payload = _as_is(db_session, world["household"])
    payload.address = AddressRow("Kerkstraat", "5", "B", "2440")
    _save(db_session, world, payload, by="Bert")
    db_session.expire_all()
    address = db_session.get(Person, world["An"].id).address
    assert address is not None, "no address was created"
    assert (address.street, address.house_number, address.bus_number) == ("Kerkstraat", "5", "B")
    assert address.postal_code.postal_code == "2440"
    assert _history(db_session, AddressHistory, address_id=address.id) == [
        ("insert", "address_created", "member_self")
    ]
    assert db_session.query(Address).count() == 1, "a household has one address"


def test_an_empty_address_section_stays_no_address(db_session):
    """All three empty is "no address", not a refusal — the section is there for
    every household, and most saves do not touch it."""
    world = _without_address(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    payload.address = AddressRow("", "", "", "")
    _save(db_session, world, payload)
    assert _counts(db_session) == before


@pytest.mark.parametrize(
    ("sent", "place"),
    [
        (("", "5", "", "2440"), "address.street"),
        (("Kerkstraat", "", "", "2440"), "address.house_number"),
        (("Kerkstraat", "5", "", ""), "address.postal_code"),
        (("", "", "B", ""), "address.street"),
    ],
)
def test_street_house_number_and_postal_code_are_required_together(db_session, sent, place):
    """As soon as one of them is filled — a bus number alone counts — the three
    are asked, at the first that is missing, and nothing is written.
    Proven red by creating the address with what was sent: a row without a street."""
    world = _without_address(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    payload.address = AddressRow(*sent)
    assert _places(db_session, world, payload) == {place: WHOLE_ADDRESS}
    assert _counts(db_session) == before


def test_an_address_that_is_there_cannot_be_emptied_in_part(db_session):
    """The same rule on an address that exists: until #1603 an emptied street was
    stored as sent. Proven red by dropping `require_whole_address` from the
    change: the street is stored empty."""
    world = _household(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    payload.address.street = ""
    assert _places(db_session, world, payload) == {"address.street": WHOLE_ADDRESS}
    assert _counts(db_session) == before
    db_session.expire_all()
    assert db_session.get(Person, world["An"].id).address.street == "Dorpsstraat"


def test_a_new_address_with_an_unknown_postal_code_is_refused_at_that_field(db_session):
    world = _without_address(db_session)
    before = _counts(db_session)
    payload = _as_is(db_session, world["household"])
    payload.address = AddressRow("Kerkstraat", "5", "", "9999")
    assert _places(db_session, world, payload) == {
        "address.postal_code": "Onbekende postcode: 9999"
    }
    assert _counts(db_session) == before


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


# ── #1853: an e-mail row is an address ───────────────────────────────────────


def _snapshot(db, world) -> list[tuple]:
    db.expire_all()
    return sorted(
        (c.person_id, c.contact_type_code, c.value, c.is_primary)
        for c in db.query(ContactDetail).filter(
            ContactDetail.person_id.in_([world["An"].id, world["Bert"].id])
        )
    )


def test_a_new_email_row_that_is_no_address_is_refused_at_its_own_field(db_session):
    """The rule of the contact detail (#1853), asked early so the refusal has a
    place the screen can mark: the row's own field. Nothing of the save is
    written — also not the good row beside it."""
    world = _household(db_session)
    before = _snapshot(db_session, world)
    payload = _as_is(db_session, world["household"])
    _row(payload, world["An"]).emails += [
        EmailRow("n1", "an zonder adres"),
        EmailRow("n2", "an.goed@example.com"),
    ]

    assert _places(db_session, world, payload) == {"e.n1.value": "Vul een geldig e-mailadres in."}
    assert _snapshot(db_session, world) == before


def test_an_existing_email_row_changed_into_no_address_is_refused_at_its_field(db_session):
    world = _household(db_session)
    before = _snapshot(db_session, world)
    payload = _as_is(db_session, world["household"])
    stored = next(e for e in _row(payload, world["An"]).emails if e.key.isdigit())
    stored.value = "an@"

    assert _places(db_session, world, payload) == {
        f"e.{stored.key}.value": "Vul een geldig e-mailadres in."
    }
    assert _snapshot(db_session, world) == before


def test_two_rows_that_are_no_address_are_each_named(db_session):
    world = _household(db_session)
    payload = _as_is(db_session, world["household"])
    _row(payload, world["An"]).emails.append(EmailRow("n1", "geen"))
    _row(payload, world["Bert"]).emails.append(EmailRow("n2", "ook geen"))

    assert set(_places(db_session, world, payload)) == {"e.n1.value", "e.n2.value"}

"""An e-mail address belongs to one person outside a household (CR-22 R4, R7, R10; #1704).

Signing in sends a code to an address, so the address has to say who signs in.
Inside one household persons may share an address — the household acts as one;
outside it, a second person with the same address is refused. Tests T7 and T8
of the change request, on made-up data.

The rule is `mdm.service.email_refusal`; every writer reaches it through
`new_contact_detail` (a new row) or `require_email_free` (another value on an
existing row).

Broken on purpose (7 October 2026), each red for its own reason: the housemates
no longer taken out of the holders → the household test; the comparison made
case-sensitive → the case test; unconfirmed rows counted → the pending-address
test; the call taken out of `new_contact_detail` → every writer test; the call
taken out of `write_email_rows`' changed-value branch → the changed-row test.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.mdm.models import (
    ContactDetail,
    EmailAddressInUse,
    Member,
    MemberPerson,
    Organization,
    Person,
)
from app.domains.mdm.service import (
    add_email_address,
    create_person_for_circle,
    email_refusal,
    new_contact_detail,
    upsert_primary_contact,
    write_email_rows,
)
from app.kernel.tenancy import TENANT_VOORBEELD_ID, current_tenant_id

pytestmark = pytest.mark.ui_agnostisch

TAKEN = "bezet@example.com"


def _person(db, first_name, *, household=None, email=None, confirmed=True, relation="HOOFDLID"):
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name=first_name, last_name="Proef"
    )
    db.add(person)
    db.flush()
    if household is not None:
        db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type=relation))
        db.flush()
    if email:
        db.add(new_contact_detail(db, person, "EMAIL", email, is_primary=True, confirmed=confirmed))
        db.flush()
    return person


def _household(db):
    household = Member()
    db.add(household)
    db.flush()
    return household


@pytest.fixture
def world(db_session):
    """One household whose main member holds TAKEN, a second household, an account."""
    first = _household(db_session)
    holder = _person(db_session, "Houder", household=first, email=TAKEN)
    partner = _person(db_session, "Partner", household=first, relation="PARTNER")
    other = _person(db_session, "Buur", household=_household(db_session))
    account = _person(db_session, "Account")
    db_session.commit()
    return holder, partner, other, account


def _emails(db, person) -> list[str]:
    """Read fresh. No rollback in these tests: the rule refuses BEFORE the
    address is written, so there is nothing of it to undo — and that is what
    the assertions after each refusal check."""
    db.expire_all()
    return sorted(
        row.value
        for row in db.query(ContactDetail).filter_by(person_id=person.id, contact_type_code="EMAIL")
    )


# ── The rule itself (T7) ─────────────────────────────────────────────────────


def test_another_households_address_is_refused(db_session, world):
    _holder, _partner, other, _account = world
    assert email_refusal(db_session, other, TAKEN) == (
        "Dit e-mailadres is al in gebruik door iemand anders."
    )


def test_an_accounts_address_is_refused_and_an_account_is_refused_a_members(db_session, world):
    """A person without a household is an account: the rule holds both ways."""
    holder, _partner, _other, account = world
    assert email_refusal(db_session, account, TAKEN)
    db_session.add(
        new_contact_detail(db_session, account, "EMAIL", "eigen@example.com", is_primary=True)
    )
    db_session.commit()
    assert email_refusal(db_session, holder, "eigen@example.com")


def test_inside_the_own_household_the_address_may_be_shared(db_session, world):
    """Red without the household exception: the partner is refused."""
    holder, partner, _other, _account = world
    assert email_refusal(db_session, partner, TAKEN) is None
    assert email_refusal(db_session, holder, TAKEN) is None, "one's own address is one's own"


def test_the_comparison_ignores_case_and_surrounding_space(db_session, world):
    _holder, _partner, other, _account = world
    assert email_refusal(db_session, other, "  Bezet@Example.COM ")
    assert email_refusal(db_session, other, "vrij@example.com") is None
    assert email_refusal(db_session, other, "") is None


def test_an_address_that_still_waits_for_its_code_claims_nothing(db_session, world):
    """Otherwise anyone could block an address by typing it."""
    _holder, _partner, other, account = world
    db_session.add(
        new_contact_detail(
            db_session, account, "EMAIL", "wacht@example.com", is_primary=True, confirmed=False
        )
    )
    db_session.commit()
    assert email_refusal(db_session, other, "wacht@example.com") is None


def test_an_organisations_address_is_no_persons_address(db_session, world):
    _holder, _partner, other, _account = world
    organisation = db_session.query(Organization).first()
    assert organisation is not None, "no seeded organisation to hang a contact on"
    db_session.add(
        ContactDetail(
            organization_id=organisation.id,
            contact_type_code="EMAIL",
            value="info@example.com",
            is_primary=True,
        )
    )
    db_session.commit()
    assert email_refusal(db_session, other, "info@example.com") is None


def test_a_removed_address_is_free_again(db_session, world):
    holder, _partner, other, _account = world
    row = db_session.query(ContactDetail).filter_by(person_id=holder.id, value=TAKEN).one()
    holder.contact_details.remove(row)
    db_session.commit()
    assert email_refusal(db_session, other, TAKEN) is None


# ── Per tenant (T8) ──────────────────────────────────────────────────────────


def test_two_tenants_may_each_have_a_person_with_the_same_address(db_session, world):
    """Accounts are per tenant (R10): the same address at two tenants is two persons."""
    token = current_tenant_id.set(TENANT_VOORBEELD_ID)
    try:
        elsewhere = _person(db_session, "Elders")
        assert email_refusal(db_session, elsewhere, TAKEN) is None
        db_session.add(new_contact_detail(db_session, elsewhere, "EMAIL", TAKEN, is_primary=True))
        db_session.commit()
    finally:
        current_tenant_id.reset(token)
    holders = (
        db_session.query(ContactDetail)
        .execution_options(include_all_tenants=True)
        .filter(ContactDetail.value == TAKEN)
    )
    assert holders.count() == 2


# ── Every writer passes it ───────────────────────────────────────────────────


def test_the_factory_refuses_and_marks_what_it_makes_as_confirmed(db_session, world):
    _holder, _partner, other, _account = world
    with pytest.raises(EmailAddressInUse):
        new_contact_detail(db_session, other, "EMAIL", TAKEN, is_primary=True)
    made = new_contact_detail(db_session, other, "EMAIL", "nieuw@example.com", is_primary=True)
    assert made.confirmed_at is not None and made.person_id == other.id
    waiting = new_contact_detail(
        db_session, other, "EMAIL", "later@example.com", is_primary=False, confirmed=False
    )
    assert waiting.confirmed_at is None
    mobile = new_contact_detail(db_session, other, "MOBILE", "0470000001", is_primary=True)
    assert mobile.confirmed_at is not None, "a number is not waited for"


def test_adding_an_address_on_the_person_screen_is_refused(db_session, world):
    _holder, _partner, other, _account = world
    with pytest.raises(EmailAddressInUse):
        add_email_address(db_session, other.id, TAKEN, actor="bestuur@example.com")
    assert _emails(db_session, other) == []


def test_a_new_row_and_a_changed_row_of_the_email_rows_are_refused(db_session, world):
    """The household's save: a typed new address, and an existing row retyped."""
    _holder, _partner, other, _account = world
    with pytest.raises(EmailAddressInUse):
        write_email_rows(db_session, other, {}, [TAKEN], actor="x@example.com")

    write_email_rows(db_session, other, {}, ["mijn@example.com"], actor="x@example.com")
    db_session.commit()
    own = db_session.query(ContactDetail).filter_by(person_id=other.id).one()
    with pytest.raises(EmailAddressInUse):
        write_email_rows(db_session, other, {own.id: TAKEN}, [], actor="x@example.com")
    assert _emails(db_session, other) == ["mijn@example.com"]


def test_the_import_and_the_board_are_refused_too(db_session, world):
    """`upsert_primary_contact` serves the member import and the board's form:
    confirmed writers, and they still pass the rule."""
    _holder, _partner, other, _account = world
    with pytest.raises(EmailAddressInUse):
        upsert_primary_contact(
            db_session, other, "EMAIL", TAKEN, action="contacts_updated", source="import", actor="x"
        )
    changed = upsert_primary_contact(
        db_session,
        other,
        "MOBILE",
        "0470000002",
        action="contacts_updated",
        source="import",
        actor="x",
    )
    assert changed is not None, "a number passes: the rule is about addresses"


def test_a_person_made_for_a_meeting_circle_is_refused_a_taken_address(db_session, world):
    organisation = db_session.query(Organization).first()
    with pytest.raises(EmailAddressInUse):
        create_person_for_circle(
            db_session,
            first_name="Gast",
            last_name="Proef",
            email=TAKEN,
            organization_id=organisation.id,
            on_day=date(2026, 10, 7),
        )
    # Refused before the person is made: the screen has nothing to undo.
    assert db_session.query(Person).filter_by(first_name="Gast").count() == 0
    assert db_session.query(ContactDetail).filter_by(value=TAKEN).count() == 1

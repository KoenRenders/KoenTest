"""The board's household record saves as a whole (#1899, CR-11 roll-out slice 1).

Until #1899 the record had eleven partial routes — a person's card, an e-mail
row added, made primary or removed, the address, a person added or removed, the
board member, a year added or removed — that each committed on their own. It
has ONE save now, `POST /admin/leden/gezin/{id}`: mdm's `save_household` with
the board as its caller, and the removed membership years handed to membership
inside the same transaction.

What this file holds is what differs for the board, and that the save is one:

- everything in one request and one transaction — a refusal writes nothing,
  also not the year that was removed in the same form;
- the history says the board did it (`admin_update`, the board member's
  address), never `member_self`;
- an e-mail address the board types counts at once (a member's waits for its
  code, CR-22 R15);
- a person the board takes out is deleted (a member's removal only takes the
  person out of the household), and the main member is refused at his card;
- the board member is saved with it; a year removed is settled as it always
  was (#619; Koen, 11 October 2026: "a" — as today): an open charge goes, a
  received amount becomes a pending refund;
- who may: `party.masterdata` changes, `party.view` reads; no change without
  the session's token.

The rules both callers share (a name, a birth date, an address that is no
address, a second main member) are held where they were, against this one
save: `test_person_name_refused_1251.py`, `test_one_main_member_1251.py`, …

Red (each restored after):
- `board` forced False in `save_household` → the history says `member_self`,
  the typed address waits, the removed person stays a person;
- `also(db)` not called → the removed years stay, with and without money on
  them;
- the `board_member` branch taken out → the board member is not written.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.mdm.api import (
    ContactDetail,
    ContactDetailHistory,
    Member,
    MemberPerson,
    Person,
    PersonHistory,
)
from app.domains.membership.api import Membership
from tests._sites import at_tenant
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    board_session,
    create_test_family,
    create_test_person,
    record_fields,
    save_record,
    seed_postal_code,
)

pytestmark = pytest.mark.ui_serverrendered

MAIN = "hoofd-1899@example.org"
NEW = "nieuw-1899@example.org"


@pytest.fixture
def world(client, db_session):
    """A household of a main member and a partner, a membership year without a
    booking, and the board signed in."""
    seed_postal_code(db_session, code="2400", municipality="Mol")
    household, main = create_test_family(db_session, email=MAIN, mobile="0470 00 00 01")
    at_tenant(db_session, household)  # CR-26 F9
    partner = create_test_person(db_session, first_name="Pia", last_name="Partner")
    db_session.add(
        MemberPerson(member_id=household.id, person_id=partner.id, relation_type="PARTNER")
    )
    year = Membership(
        member_id=household.id,
        year=2020,
        is_active=True,
        valid_from=date(2020, 1, 1),
        valid_to=date(2020, 12, 31),
    )
    db_session.add(year)
    db_session.commit()
    board_session(client)
    return {"id": household.id, "main": main.id, "partner": partner.id, "year": year.id}


def _add_person(fields: dict, key: str = "n1", **more) -> None:
    fields["h_order"] = [*fields["h_order"], key]
    fields.update(
        {
            f"h.{key}.first_name": "Kim",
            f"h.{key}.last_name": "Kind",
            f"h.{key}.date_of_birth": "2012-03-04",
            f"h.{key}.gender_code": "F",
            f"h.{key}.relation_type": "KIND",
            **{f"h.{key}.{name}": value for name, value in more.items()},
        }
    )


def test_one_request_writes_everything_the_record_holds(client, db_session, world):
    board = create_test_person(db_session, first_name="Bea", last_name="Bestuur")
    db_session.commit()
    fields = record_fields(client, world["id"])
    fields[f"h.{world['main']}.first_name"] = "Anders"
    fields[f"h.{world['partner']}.relation_type"] = "KIND"
    fields.update(
        {
            "address.street": "Kerkstraat",
            "address.house_number": "12",
            "address.postal_code": "2400",
            "board_member_id": str(board.id),
        }
    )
    _add_person(fields)
    fields[f"e_order.{world['main']}"] = [*fields[f"e_order.{world['main']}"], "nx"]
    fields["e.nx.value"] = NEW
    fields["y_order"] = []

    answer = save_record(client, world["id"], fields)
    assert answer.status_code == 200, answer.text[:400]
    assert 'data-mode="read"' in answer.text and "data-toast" in answer.text
    assert answer.headers["HX-Push-Url"] == f"/admin/leden/gezin/{world['id']}"

    db_session.expire_all()
    household = db_session.get(Member, world["id"])
    main = db_session.get(Person, world["main"])
    assert main.first_name == "Anders"
    assert main.address.street == "Kerkstraat" and main.address.house_number == "12"
    assert household.board_member_id == board.id
    links = {
        link.person.first_name: link.relation_type.value
        for link in household.member_persons
        if link.deleted_at is None
    }
    assert links == {"Anders": "HOOFDLID", "Pia": "KIND", "Kim": "KIND"}
    addresses = {c.value for c in main.contact_details if c.contact_type_code == "EMAIL"}
    assert addresses == {MAIN, NEW}
    assert db_session.query(Membership).filter(Membership.id == world["year"]).first() is None, (
        "the removed year is still there"
    )


def test_the_history_says_the_board_did_it(client, db_session, world):
    fields = record_fields(client, world["id"])
    fields[f"h.{world['main']}.first_name"] = "Anders"
    assert save_record(client, world["id"], fields).status_code == 200
    rows = (
        db_session.query(PersonHistory)
        .filter(PersonHistory.person_id == world["main"], PersonHistory.action == "person_updated")
        .all()
    )
    assert [(row.source, row.actor) for row in rows] == [("admin_update", SEEDED_ADMIN_EMAIL)]


def test_an_address_the_board_types_counts_at_once(client, db_session, world):
    """A member's own address waits for its code (CR-22 R15); the board's does
    not — it is confirmed, and it may be the main address in the same save."""
    fields = record_fields(client, world["id"])
    fields[f"e_order.{world['partner']}"] = ["nx"]
    fields["e.nx.value"] = NEW
    fields[f"e_primary.{world['partner']}"] = "nx"
    assert save_record(client, world["id"], fields).status_code == 200
    db_session.expire_all()
    row = db_session.query(ContactDetail).filter(ContactDetail.value == NEW).one()
    assert row.person_id == world["partner"]
    assert row.confirmed_at is not None, "the board's address waits for a code"
    assert row.is_primary
    history = db_session.query(ContactDetailHistory).filter_by(contact_detail_id=row.id).all()
    assert {h.source for h in history} == {"admin_update"}


def test_a_person_the_board_takes_out_is_deleted(client, db_session, world):
    fields = record_fields(client, world["id"])
    fields["h_order"] = [key for key in fields["h_order"] if key != str(world["partner"])]
    assert save_record(client, world["id"], fields).status_code == 200
    db_session.expire_all()
    assert db_session.get(Person, world["partner"]) is None, "the person is only taken out"
    deleted = (
        db_session.query(PersonHistory)
        .filter(
            PersonHistory.person_id == world["partner"], PersonHistory.action == "person_deleted"
        )
        .count()
    )
    assert deleted == 1


def test_the_main_member_is_refused_at_his_card_and_nothing_is_written(client, db_session, world):
    """The refusal of the one rule (a household has a main member), at the card
    the form removed — and with it the whole save: the year removed in the same
    form stays."""
    fields = record_fields(client, world["id"])
    fields["h_order"] = [key for key in fields["h_order"] if key != str(world["main"])]
    fields[f"h.{world['partner']}.first_name"] = "Nietbewaard"
    fields["y_order"] = []
    answer = save_record(client, world["id"], fields)
    assert answer.status_code == 422
    assert f"h.{world['main']}" in answer.text
    db_session.expire_all()
    assert db_session.get(Person, world["main"]) is not None
    assert db_session.get(Person, world["partner"]).first_name == "Pia"
    assert db_session.query(Membership).filter(Membership.id == world["year"]).first() is not None


def test_a_refused_field_keeps_the_year_that_was_removed_with_it(client, db_session, world):
    fields = record_fields(client, world["id"])
    fields[f"h.{world['partner']}.first_name"] = ""
    fields["y_order"] = []
    answer = save_record(client, world["id"], fields)
    assert answer.status_code == 422
    assert f"h.{world['partner']}.first_name" in answer.text
    db_session.expire_all()
    assert db_session.query(Membership).filter(Membership.id == world["year"]).first() is not None


def test_a_board_member_that_does_not_exist_is_refused(client, db_session, world):
    fields = record_fields(client, world["id"])
    fields["board_member_id"] = "999999"
    answer = save_record(client, world["id"], fields)
    assert answer.status_code == 422
    db_session.expire_all()
    assert db_session.get(Member, world["id"]).board_member_id is None


def test_the_board_member_is_taken_away_again(client, db_session, world):
    board = create_test_person(db_session, first_name="Bea", last_name="Bestuur")
    db_session.get(Member, world["id"]).board_member_id = board.id
    db_session.commit()
    read = client.get(f"/admin/leden/gezin/{world['id']}").text
    assert "Bea Bestuur" in read
    fields = record_fields(client, world["id"])
    assert fields["board_member_id"] == str(board.id)
    fields["board_member_id"] = ""
    assert save_record(client, world["id"], fields).status_code == 200
    db_session.expire_all()
    assert db_session.get(Member, world["id"]).board_member_id is None


def test_a_removed_year_with_money_is_settled_as_it_always_was(client, db_session, world):
    """Koen, 11 October 2026, to the choice between settling as today and
    refusing: "a". An open charge goes with its year; a received amount becomes
    a pending refund for the treasurer (#619)."""
    from app.domains.payment.api import PaymentRecord, create_payment_record

    paid = Membership(
        member_id=world["id"],
        year=2021,
        is_active=True,
        valid_from=date(2021, 1, 1),
        valid_to=date(2021, 12, 31),
    )
    db_session.add(paid)
    db_session.flush()
    open_charge = create_payment_record(
        db_session, "membership", world["year"], amount=Decimal("35.00"), method="transfer"
    )
    paid_charge = create_payment_record(
        db_session, "membership", paid.id, amount=Decimal("35.00"), method="transfer"
    )
    paid_charge.amount_paid = Decimal("35.00")
    db_session.commit()
    open_id, paid_id, paid_year = open_charge.id, paid_charge.id, paid.id

    fields = record_fields(client, world["id"])
    fields["y_order"] = []
    assert save_record(client, world["id"], fields).status_code == 200
    db_session.expire_all()
    assert db_session.query(Membership).filter(Membership.member_id == world["id"]).count() == 0
    assert db_session.query(PaymentRecord).filter(PaymentRecord.id == open_id).first() is None
    kept = db_session.query(PaymentRecord).filter(PaymentRecord.id == paid_id).one()
    assert kept.amount_paid == Decimal("35.00"), "a received amount is a fact: it stays"
    refunds = (
        db_session.query(PaymentRecord)
        .filter(PaymentRecord.payable_id == paid_year, PaymentRecord.refund_of_id == paid_id)
        .all()
    )
    assert len(refunds) == 1 and refunds[0].amount_paid is None, "no pending refund was raised"


def test_a_year_of_another_household_is_not_touched(client, db_session, world):
    """The save removes the years of ITS household that the form no longer
    holds — a key the form adds from elsewhere does nothing."""
    other, _person = create_test_family(db_session, email="ander-1899@example.org")
    at_tenant(db_session, other)  # CR-26 F9
    theirs = Membership(member_id=other.id, year=2020, is_active=True)
    db_session.add(theirs)
    db_session.commit()
    fields = record_fields(client, world["id"])
    fields["y_order"] = [str(theirs.id)]
    assert save_record(client, world["id"], fields).status_code == 200
    db_session.expire_all()
    assert db_session.query(Membership).filter(Membership.id == theirs.id).first() is not None
    assert db_session.query(Membership).filter(Membership.id == world["year"]).first() is None


def test_who_may_read_and_who_may_change(client, db_session, world):
    """`party.masterdata` changes; without the session's token nothing does."""
    fields = record_fields(client, world["id"])
    fields[f"h.{world['main']}.first_name"] = "Zondertoken"
    answer = save_record(client, world["id"], fields, headers={})
    assert answer.status_code == 403
    db_session.expire_all()
    assert db_session.get(Person, world["main"]).first_name != "Zondertoken"


def test_the_record_reads_first_and_edits_with_one_form(client, db_session, world):
    read = client.get(f"/admin/leden/gezin/{world['id']}").text
    assert 'data-mode="read"' in read and '<form id="gezin-form"' not in read
    assert read.count("data-person-card") == 2
    assert f'href="/admin/leden/gezin/{world["id"]}?bewerken=1"' in read
    assert "data-summary-card" in read and "data-related-tabs" in read
    edit = client.get(f"/admin/leden/gezin/{world['id']}?bewerken=1").text
    assert edit.count('<form id="gezin-form"') == 1 and edit.count("data-action-bar") == 1
    assert edit.count("data-summary-card") == 1, "#1912: the same card while editing"
    assert f'hx-post="/admin/leden/gezin/{world["id"]}"' in edit
    # Nothing on the page saves on its own: the one form, and the delete of the
    # household, are the only posts it holds.
    import re

    posts = set(re.findall(r'hx-post="([^"]+)"', edit[edit.index('id="gezin-record"') :]))
    assert posts == {
        f"/admin/leden/gezin/{world['id']}",
        f"/admin/leden/gezin/{world['id']}/verwijderen",
    }, posts

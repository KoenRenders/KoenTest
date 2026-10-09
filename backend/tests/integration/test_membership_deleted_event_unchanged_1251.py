"""CR-13 phase 4c, C7-2 (#1251): the money follows a deleted membership through an
event — what is written stays.

When the board deletes a membership, or a household with its memberships, the
charges of that membership follow (#619): an open charge goes, a paid amount
stays as a fact and gets one pending refund for the treasurer to confirm. Until
C7-2 membership called `payment.api.reconcile_charges` for it — a command of
another domain, with no answer. It is a fact now: membership publishes
`MembershipDeleted` (`kernel/contracts/membership.py`) and payment subscribes
(`payment/handlers.py`), in the same transaction.

No behaviour changes, so the proof is **the same answer and the same rows on the
same input**: each case below — the screen's answer, the memberships, every
payment record of the membership and every history row of those records — was
recorded on the code BEFORE the event and the code with the event must give it
again, character for character (`tests/_snapshot.py`).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Address, ContactDetail, Member, MemberPerson, Person
from app.domains.membership.api import Membership
from app.domains.payment.api import PayableType, PaymentRecord
from app.domains.payment.models import PaymentRecordHistory
from tests import payments_door
from tests._snapshot import compare, fixed_ids, normalise
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_postal_code, sign_up_at_the_door

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "membership_deleted_1251"
BEFORE = "the money followed a deleted membership through an event (CR-13 phase 4c, C7-2)"
MODELS = (Member, Person, MemberPerson, Address, ContactDetail, Membership, PaymentRecordHistory)
EMAIL = "geschrapt-1251@example.com"


def _login(client) -> dict[str, str]:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


@pytest.fixture
def household(client, db_session):
    """A household that signed up and pays by transfer: one membership, not yet
    active, and its open charge."""
    with fixed_ids(db_session, MODELS):
        seed_postal_code(db_session)
        answer = sign_up_at_the_door(
            client,
            json={
                "street": "Milostraat",
                "house_number": "40",
                "postal_code": "2400",
                "payment_method": "transfer",
                "members": [
                    {
                        "last_name": "Geschrapt",
                        "first_name": "Jan",
                        "email": EMAIL,
                        "mobile": "0470000000",
                        "date_of_birth": "1980-01-01",
                        "gender_code": "M",
                        "relation_type": "HOOFDLID",
                    }
                ],
            },
        )
        assert answer.status_code == 201, answer.json()
        yield db_session.query(Membership).one()


def _records(db, membership_id: int) -> list[PaymentRecord]:
    """The payment records of the membership, deleted ones too, oldest first."""
    return (
        db.query(PaymentRecord)
        .execution_options(include_deleted=True)
        .filter(
            PaymentRecord.payable_type == PayableType.MEMBERSHIP,
            PaymentRecord.payable_id == membership_id,
        )
        .order_by(PaymentRecord.created_at, PaymentRecord.type)
        .all()
    )


def _rows(db, membership_id: int) -> str:
    """The membership (deleted or not), every payment record of it and every
    history row of those records — with the ids of the records replaced by their
    order, since a payment record's id is random."""
    db.expire_all()
    lines = []
    memberships = (
        db.query(Membership).execution_options(include_deleted=True).order_by(Membership.id)
    )
    for membership in memberships:
        lines.append(
            f"membership {membership.id}: active={membership.is_active} "
            f"deleted={'yes' if membership.deleted_at else 'no'}"
        )
    records = _records(db, membership_id)
    order = {record.id: f"<RECORD-{n}>" for n, record in enumerate(records, 1)}
    # The price of a membership depends on the day it is bought: the recording
    # says PRICE and -PRICE, so it reads the same in January and in October.
    price = records[0].amount

    def money(value) -> str:
        return {price: "PRICE", -price: "-PRICE"}.get(value, str(value))

    for record in records:
        lines.append(
            f"record {order[record.id]}: {record.type} {record.status} {record.method} "
            f"amount={money(record.amount)} paid={money(record.amount_paid)} "
            f"refund_of={order.get(record.refund_of_id, record.refund_of_id)} "
            f"note={record.note!r} deleted={'yes' if record.deleted_at else 'no'}"
        )
    history = (
        db.query(PaymentRecordHistory)
        .filter(PaymentRecordHistory.payment_record_id.in_(order))
        .order_by(PaymentRecordHistory.id)
    )
    for row in history:
        lines.append(
            f"history {order[row.payment_record_id]}: {row.operation} {row.action} "
            f"source={row.source} actor={row.actor} status={row.status} "
            f"amount={money(row.amount)} paid={money(row.amount_paid)} note={row.note!r}"
        )
    return "\n".join(lines)


def _record_case(name: str, response, db, membership_id: int) -> None:
    today = date.today()
    moving = {today.isoformat(): "<TODAY>", str(today.year): "<YEAR>"}
    got = normalise(f"{response.status_code}\n--- rows ---\n{_rows(db, membership_id)}", {}, moving)
    compare(SNAPSHOTS, name, got, BEFORE)


def _delete_membership(client, membership) -> object:
    return client.post(
        f"/admin/leden/gezin/{membership.member_id}/lidmaatschappen/{membership.id}/verwijderen",
        headers=_login(client),
    )


def _pay(client, db, membership_id: int) -> None:
    [record] = _records(db, membership_id)
    paid = payments_door.update(client, record.id, {"status": "paid"})
    assert paid.status_code == 200, paid.text


def test_an_unpaid_membership_is_deleted_as_it_was(client, db_session, household):
    """The open charge goes with the membership."""
    response = _delete_membership(client, household)
    _record_case("membership_unpaid", response, db_session, household.id)


def test_a_paid_membership_is_deleted_as_it_was(client, db_session, household):
    """The paid amount stays and gets one pending refund."""
    _pay(client, db_session, household.id)
    response = _delete_membership(client, household)
    _record_case("membership_paid", response, db_session, household.id)


def test_a_household_with_a_paid_membership_is_deleted_as_it_was(client, db_session, household):
    """Deleting the household deletes its memberships, and each one's money follows."""
    _pay(client, db_session, household.id)
    response = client.post(
        f"/admin/leden/gezin/{household.member_id}/verwijderen", headers=_login(client)
    )
    _record_case("household_paid", response, db_session, household.id)


def test_deleting_into_silence_is_refused(db_session, household, monkeypatch):
    """The money following is not optional: with nothing subscribed to
    `MembershipDeleted` (payment's handlers not imported) the deletion fails
    loudly instead of leaving an open charge behind."""
    from app.domains.membership.api import delete_membership
    from app.kernel import events
    from app.kernel.contracts.membership import MembershipDeleted
    from tests.conftest import seeded_admin

    membership_id = household.id
    admin = seeded_admin(db_session)
    monkeypatch.delitem(events._subscribers, MembershipDeleted)
    # A RuntimeError, not a refusal: the door answers a 500 and its transaction
    # is rolled back — the deletion does not go through half.
    with pytest.raises(RuntimeError, match="MembershipDeleted"):
        delete_membership(db_session, membership_id, admin=admin)

"""What the master-data component does when another component says something happened.

Events, not calls (CR-13 §B4.9): a component that wants a circle relation changed
publishes an event; `mdm`, which owns the relation, subscribes here. Handlers run
synchronously, in the publisher's transaction, and never commit — the door service
does, once (§B4.1).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.domains.mdm.service import create_account_person, set_circle_start
from app.kernel.contracts.auth import AccountCodeEntered
from app.kernel.contracts.meetings import CircleStartChosen
from app.kernel.events import subscribe


@subscribe(CircleStartChosen)
def set_circle_start_when_chosen(event: CircleStartChosen, db: Session) -> None:
    """Store the chosen start date (#1346); `OrganizationPerson.check()` refuses a
    start after the end, and the refusal reaches the publisher."""
    set_circle_start(db, event.relation_id, date.fromisoformat(event.start_date))


#: The origin of an account's rows in the history: the person made them himself.
ACCOUNT_SOURCE = "account"


@subscribe(AccountCodeEntered)
def make_account_when_code_entered(event: AccountCodeEntered, db: Session) -> None:
    """Make the person of a new account, with its history (CR-22 R3, #1707).

    `create_account_person` refuses an address that got an owner since the
    form was sent (`EmailAddressInUse`); the refusal reaches the publisher,
    which spends the code and makes nobody.
    """
    from app.domains.audit.api import snapshot_contact_detail, snapshot_person

    person, details = create_account_person(
        db,
        first_name=event.first_name,
        last_name=event.last_name,
        email=event.email,
        mobile=event.mobile,
    )
    snapshot_person(
        db,
        person,
        operation="insert",
        action="account_created",
        source=ACCOUNT_SOURCE,
        actor=event.email,
    )
    for detail in details:
        snapshot_contact_detail(
            db,
            detail,
            operation="insert",
            action="account_created",
            source=ACCOUNT_SOURCE,
            actor=event.email,
        )

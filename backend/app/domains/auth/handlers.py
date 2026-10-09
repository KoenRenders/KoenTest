"""What the auth component does when another component says something happened.

Events, not calls (CR-13 §B4.9): `mdm` owns a person's addresses and says that
one waits for its code; `auth`, which owns every code the portal sends, issues
it here. Handlers run synchronously, in the publisher's transaction, and never
commit — the door service does, once (§B4.1).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.auth.login import issue_address_code
from app.domains.auth.service import give_board_member_a_login
from app.kernel.contracts.mdm import BoardMemberReported, EmailAddressAdded
from app.kernel.events import subscribe


@subscribe(EmailAddressAdded)
def send_address_code(event: EmailAddressAdded, db: Session) -> None:
    """A code for the address that waits (CR-22 R15, F6; #1711): the token and
    its mail, both in the transaction that stored the row. The mail is a job:
    it leaves after that commit, so never for a row that was not stored."""
    issue_address_code(
        db,
        contact_id=event.contact_id,
        email=event.email,
        replaces_id=event.replaces_id,
        replaces_email=event.replaces_email,
        make_primary=event.make_primary,
    )


@subscribe(BoardMemberReported)
def give_reported_board_member_a_login(event: BoardMemberReported, db: Session) -> None:
    """The member report names a board member with an address and no login: auth,
    which owns every login, makes it (CR-13 phase 4c, #1251) — in the import's
    transaction."""
    give_board_member_a_login(db, event.email)

"""Every new person and organisation gets its party (CR-26 F1, #2020).

A party is the one thing every "someone" points at; a person and an
organisation each hang on one (`party_id`, NOT NULL). It is made here, in the
same flush, on the same account — the one the row was given, or the current
tenant's through the default — so no writer has to remember it. Imported by
`mdm.models`, so the listener stands wherever the models do.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.domains.mdm.models import Organization, Party, PartyKind, Person


@event.listens_for(Session, "before_flush")
def _parties_for_new_rows(session, _flush_context, _instances) -> None:
    for row in list(session.new):
        if isinstance(row, (Person, Organization)) and row.party is None and row.party_id is None:
            kind = PartyKind.PERSON if isinstance(row, Person) else PartyKind.ORGANIZATION
            row.party = Party(kind=kind, account_id=row.account_id)

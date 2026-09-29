"""What the master-data component does when another component says something happened.

Events, not calls (CR-13 §B4.9): a component that wants a circle relation changed
publishes an event; `mdm`, which owns the relation, subscribes here. Handlers run
synchronously, in the publisher's transaction, and never commit — the door service
does, once (§B4.1).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.domains.mdm.service import set_circle_start
from app.kernel.contracts.meetings import CircleStartChosen
from app.kernel.events import subscribe


@subscribe(CircleStartChosen)
def set_circle_start_when_chosen(event: CircleStartChosen, db: Session) -> None:
    """Store the chosen start date (#1346); `OrganizationPerson.check()` refuses a
    start after the end, and the refusal reaches the publisher."""
    set_circle_start(db, event.relation_id, date.fromisoformat(event.start_date))

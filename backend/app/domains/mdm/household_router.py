"""The family portal's mutations as JSON (CR-13 phase 3, #1250).

A member changes a person of their own household, adds one, or removes one. The
household and its persons are master data, so these doors are `mdm`'s (Koen, 27
September 2026: *"gezin en personen is mdm"*); until this phase they stood in
`membership/household_router.py`, which keeps the household view and the renewal.
Paths unchanged.

A door and nothing else: who is logged in (`require_member`, never the request's
word for it), the household derived from that, and the status code. The rules and
the audit rows are the service's (`household_service.py`).

Never editable here: the relation type, the household's board member, the external
member number — admin only.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import require_member
from app.domains.mdm.household_doors import household_refusals_as_http
from app.domains.mdm.household_service import (
    actor_of,
    add_household_person,
    household_of,
    person_payload,
    remove_household_person,
    update_household_person,
)

router = APIRouter(tags=["member-self"])


@router.put("/member/household/persons/{person_id}")
def update_person(
    person_id: int,
    data: dict,
    person=Depends(require_member),
    db: Session = Depends(get_db),
):
    with household_refusals_as_http():
        household = household_of(db, person)
        target = update_household_person(db, household, person_id, data, actor=actor_of(person))
    return person_payload(target)


@router.post("/member/household/persons", status_code=201)
def add_person(
    data: dict,
    person=Depends(require_member),
    db: Session = Depends(get_db),
):
    with household_refusals_as_http():
        household = household_of(db, person)
        added = add_household_person(db, household, data, actor=actor_of(person))
    return person_payload(added)


@router.delete("/member/household/persons/{person_id}", status_code=204)
def remove_person(
    person_id: int,
    person=Depends(require_member),
    db: Session = Depends(get_db),
):
    with household_refusals_as_http():
        household = household_of(db, person)
        remove_household_person(db, household, person_id, by=person, actor=actor_of(person))

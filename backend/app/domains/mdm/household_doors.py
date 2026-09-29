"""What a refusal of the household service answers at a door (CR-13 phase 3, #1250).

The service raises one kind of `MasterDataError` per answer; the doors — the
portal's JSON routes and its screen routes, and `membership`'s household view and
renewal — turn it into the status code the routes gave when the rules were theirs.
One table, so the doors cannot drift apart.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException

from app.domains.mdm.household_service import (
    CannotRemoveSelf,
    HouseholdNotFound,
    HouseholdRefused,
    OutsideHousehold,
    PersonNotFound,
)
from app.domains.mdm.models import MasterDataError, PersonDetailsMissing

STATUS = {
    HouseholdNotFound: 404,
    PersonNotFound: 404,
    OutsideHousehold: 403,
    CannotRemoveSelf: 400,
    HouseholdRefused: 422,
    PersonDetailsMissing: 422,
}


@contextmanager
def household_refusals_as_http() -> Iterator[None]:
    """A refusal of the household service becomes the status code of this door."""
    try:
        yield
    except MasterDataError as refusal:
        status = STATUS.get(type(refusal))
        if status is None:
            raise
        raise HTTPException(status_code=status, detail=str(refusal)) from refusal

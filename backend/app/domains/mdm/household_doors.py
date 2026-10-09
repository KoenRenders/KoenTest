"""What a refusal of the household service answers at a door (CR-13 phase 3, #1250).

The service raises one kind of `MasterDataError` per answer; the doors — the
portal's JSON routes and its screen routes, and `membership`'s household view and
renewal — turn it into the status code the routes gave when the rules were theirs.
One table, so the doors cannot drift apart.
"""

from __future__ import annotations

import functools
import inspect
from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException
from fastapi.responses import Response

from app.domains.mdm.household_service import (
    CannotRemoveSelf,
    HouseholdNotFound,
    HouseholdRefused,
    MainMemberStays,
    OutsideHousehold,
    PersonNotFound,
)
from app.domains.mdm.models import EmailAddressInUse, MasterDataError, PersonDetailsMissing
from app.kernel.refusals import FieldError

STATUS = {
    HouseholdNotFound: 404,
    PersonNotFound: 404,
    OutsideHousehold: 403,
    CannotRemoveSelf: 400,
    MainMemberStays: 400,
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


#: What a card's save or delete may answer as a refusal the board can do
#: something about. A 404 is not one: the household or the person is gone.
_REFUSALS = (400, 409, 422)


def says_why_in(line: str):
    """A refusal of this route goes to the message line of ITS card (#1831).

    The household screen has a form per card. Until #1831 every refusal of one
    answered a bare JSON error, and the screen showed the kit's general message —
    "Er ging iets mis … probeer opnieuw" — for something no retry would mend. The
    rule's own sentence existed and never reached the screen.

    `line` is the selector of the card's message line, with the route's path
    parameters in braces (`#persoon-{person_id}-melding`). The answer is the kit's
    `refusal_response` — the banner alone, so the card keeps what was typed and the
    other cards are not touched. The sentence stands under "Opslaan is niet
    gelukt." as a whole-form message: the kit's record form, which marks the
    field itself, serves one form per page and this page has five.
    """

    def wrap(route):
        def refused(refusal: Exception, kwargs: dict) -> Response:
            # An address in use is mdm's own refusal, which the application
            # answers as a JSON 422 for every other door (`main.py`).
            if isinstance(refusal, HTTPException):
                if refusal.status_code not in _REFUSALS:
                    raise refusal
                words = str(refusal.detail)
            else:
                words = str(refusal)
            from app.ui import refusal_response

            sentence = FieldError("", words)
            return refusal_response(kwargs["request"], [sentence], line.format(**kwargs))

        if inspect.iscoroutinefunction(route):

            @functools.wraps(route)
            async def answering(**kwargs):
                try:
                    return await route(**kwargs)
                except (HTTPException, EmailAddressInUse) as refusal:
                    return refused(refusal, kwargs)

            return answering

        @functools.wraps(route)
        def answering_sync(**kwargs):
            try:
                return route(**kwargs)
            except (HTTPException, EmailAddressInUse) as refusal:
                return refused(refusal, kwargs)

        return answering_sync

    return wrap

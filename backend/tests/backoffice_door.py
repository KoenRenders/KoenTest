"""The tests' way to the change feeds, in process (CR-13 phase 4b, #1251).

The three JSON routes under `/api/v1/admin` that answered the change feeds had no
caller but tests and are gone. Each was a door over one function of
`audit.changes`, which the Changes screen reads through `audit.api`. The tests
that used the routes prove what a change looks like in the feed — an import, a
deletion, a payment with its person and address — so they keep asking the same
functions, and read the answer as the routes gave it: JSON-shaped rows in an
`Answer` with its status code.
"""

from __future__ import annotations

from datetime import date

from fastapi.encoders import jsonable_encoder

from app.domains.audit import api as audit_api
from tests.forms_door import Answer, _db


def _day(since: date | str) -> date:
    return since if isinstance(since, date) else date.fromisoformat(since)


def member_changes(client, since: date | str) -> Answer:
    """Every change to member data since a day, as the Changes screen lists them."""
    db = _db(client)
    db.flush()
    return Answer(200, jsonable_encoder(audit_api.member_changes_since(db, _day(since))))


def changes(
    client, since: date | str, *, group: str | None = None, actor: str | None = None
) -> Answer:
    """The one feed of every change since a day, optionally one group or one actor."""
    db = _db(client)
    db.flush()
    rows = audit_api.all_changes_since(db, _day(since), group=group, actor=actor)
    return Answer(200, jsonable_encoder({"groups": audit_api.GROUPS, "rows": rows}))


def member_changes_ods(client, since: date | str) -> bytes:
    """The member changes since a day as a spreadsheet."""
    db = _db(client)
    db.flush()
    return audit_api.build_member_changes_ods(audit_api.member_changes_since(db, _day(since)))

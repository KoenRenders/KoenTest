"""Refuses a table that points at a person and an organisation, or a new such pointer outside `mdm` · ratchet · since #2020.

CR-26 C7 (the pointer gate), landing with phase 3: what hangs on a person or an
organisation hangs on its party, by one `party_id`.

- **The pair is refused outright**: no table carries both a `person_id` and an
  `organization_id`. Until phase 3 addresses and contact details did (#924,
  #945), and their history tables with them.
- **A new pointer outside `mdm` is refused** behind a baseline that only
  shrinks: the columns that point at a person by `person_id` (or at an
  organisation by `organization_id`) in another domain stay — a person's id does
  not change, and CR-26 C2 keeps them — but no new one joins them. The baseline
  is what stood on master when the gate landed (B7 counted eight on `d23caea5`;
  the meeting circle's moved into `mdm` since, seven are left).

`mdm.organization_persons` was the one table that carried the pair; CR-26 phase 2 made it
`party_relationships` (a `from_party_id` and a `to_party_id`), so the pair gate is hard and has no
baseline any more.

Proven red, additively (put back each time), on a test model too: a `person_id`
and an `organization_id` column added to `ContactDetail` → the first test names
`mdm.contact_details`; a `person_id` column added to `Membership` → the second
test names `membership.memberships.person_id`; and the gate's own functions are
run on a throwaway table below.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, Table

import app.models  # noqa: F401 - registers every model
from app.database import Base

POINTERS = ("person_id", "organization_id")

#: The pointers outside `mdm` on master when the gate landed. Only shrinks.
OUTSIDE_BASELINE = {
    "activities.activity_organisers.person_id",
    "activities.registration_history.person_id",
    "activities.registrations.person_id",
    "meetings.meeting_attendances.person_id",
    "newsletter.subscribers.person_id",
    "sales.sales_orders.person_id",
    "sales.shop_contacts.person_id",
}


def _pairs(metadata: MetaData) -> set[str]:
    return {
        table.fullname
        for table in metadata.tables.values()
        if all(name in table.c for name in POINTERS)
    }


def _outside(metadata: MetaData) -> set[str]:
    return {
        f"{table.fullname}.{name}"
        for table in metadata.tables.values()
        if table.schema != "mdm"
        for name in POINTERS
        if name in table.c
    }


def test_no_table_points_at_a_person_and_an_organisation():
    pairs = _pairs(Base.metadata)
    assert len(Base.metadata.tables) >= 100, "the gate looks at too few tables"
    assert not pairs, f"{sorted(pairs)} points at a person and an organisation: point at a party"


def test_no_new_pointer_outside_mdm():
    found = _outside(Base.metadata)
    assert len(Base.metadata.tables) >= 100, "the gate looks at too few tables"
    gone = OUTSIDE_BASELINE - found
    assert not gone, f"{sorted(gone)} is gone: take it out of OUTSIDE_BASELINE"
    new = found - OUTSIDE_BASELINE
    assert not new, (
        f"{sorted(new)} is a new pointer at a person or an organisation: point at a party"
    )


def test_the_gate_sees_a_test_model():
    metadata = MetaData()
    Table(
        "both",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("person_id", Integer),
        Column("organization_id", Integer),
        schema="elsewhere",
    )
    assert _pairs(metadata) == {"elsewhere.both"}
    assert _outside(metadata) == {"elsewhere.both.person_id", "elsewhere.both.organization_id"}

"""An organisation with two e-mail addresses: the form reads and writes the primary (CR-26 phase 3, #2020).

Since migration 315 an organisation may hold two contacts of one kind (C4.10).
The organisation's form has one input per kind, so the row it shows, edits and
empties must be the same every time: the primary, else the oldest
(`organization_service._in_order`). Without an order the reader kept whichever
row the database returned last, and a save edited or deleted whichever came
first — dev2's review of the PR, point 1.

The secondary is written first, so it has the lower id and comes first in an
unordered read: that is what makes the test able to go red.

Proven red, additively (put back each time): `return [model.id]` added at the
top of `_in_order` → the form shows the secondary, and the save changes it.
"""

from __future__ import annotations

import pytest

from app.domains.mdm.api import (
    ContactDetail,
    create_organization,
    organization_details,
    party_contacts,
    update_organization_details,
)

SECONDARY = "tweede-cr26@example.org"
PRIMARY = "hoofd-cr26@example.org"


@pytest.fixture
def organisation(db_session):
    organisation = create_organization(db_session, name="Twee Adressen vzw")
    db_session.flush()
    for value, primary in ((SECONDARY, False), (PRIMARY, True)):
        db_session.add(
            ContactDetail(
                party_id=organisation.party_id,
                account_id=organisation.account_id,
                contact_type_code="EMAIL",
                value=value,
                is_primary=primary,
            )
        )
    db_session.commit()
    return organisation


def _emails(db, organisation) -> set[str]:
    db.expire_all()
    return {
        c.value
        for c in db.query(ContactDetail)
        .filter(ContactDetail.party_id == organisation.party_id)
        .execution_options(include_all_tenants=True)
    }


def test_the_form_and_the_footer_show_the_primary(db_session, organisation):
    assert organization_details(db_session, organisation.id)["email"] == PRIMARY
    assert party_contacts(db_session, organisation.party_id)["EMAIL"] == PRIMARY


def test_a_save_changes_the_primary_and_leaves_the_other(db_session, organisation):
    update_organization_details(db_session, organisation.id, {"email": "nieuw-cr26@example.org"})
    assert _emails(db_session, organisation) == {SECONDARY, "nieuw-cr26@example.org"}


def test_an_emptied_field_removes_the_primary_and_leaves_the_other(db_session, organisation):
    update_organization_details(db_session, organisation.id, {"email": ""})
    assert _emails(db_session, organisation) == {SECONDARY}

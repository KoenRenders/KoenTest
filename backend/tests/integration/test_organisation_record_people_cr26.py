"""The card *Personen* on an organisation's record (CR-26 phase 2, C9).

The record lists who is linked to the organisation — in its circle or acting for it —
with the relation in words and its period; an ended relation stays, with its end date.

Red proof (19 October 2026, put back): `end_date` left out of the card's line -> the
ended relation reads as still open.
"""

from __future__ import annotations

from datetime import date

from app.domains.mdm.api import act_for, create_organization, end_acts_for
from app.domains.mdm.models import PartyRelationship
from app.domains.reporting.tests.test_reporting_panel_ui import login
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_person


def test_the_record_lists_who_acts_for_the_organisation_and_since_when(
    platform_workspace, db_session
):
    client = platform_workspace
    organisation = create_organization(db_session, name="Met Personen vzw")
    db_session.commit()
    person = create_test_person(db_session)
    account = db_session.get(type(organisation), organisation.id).account_id
    person.account_id = account
    db_session.flush()
    act_for(db_session, person.id, organisation.id, on_day=date(2026, 3, 1))
    db_session.commit()
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("OPERATOR",))

    card = client.get(f"/admin/organisaties/{organisation.id}").text
    card = card[card.index('id="org-section-people"') :]
    line = card[card.index(f'data-person-link="{person.id}"') :]
    line = line[: line.index("</p>")]
    assert "Treedt op namens" in line and "sinds" in line and "01-03-2026" in line
    assert "tot" not in line.replace("Treedt", "")

    end_acts_for(db_session, person.id, organisation.id, on_day=date(2026, 4, 1))
    db_session.commit()
    card = client.get(f"/admin/organisaties/{organisation.id}").text
    line = card[card.index(f'data-person-link="{person.id}"') :]
    assert "tot 01-04-2026" in line[: line.index("</p>")].replace("\n", " ")
    assert db_session.query(PartyRelationship).filter_by(kind="ACTS_FOR").count() == 1

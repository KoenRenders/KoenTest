"""#1327 — after a refusal, "Word lid" shows every person again, with their values.

Found with #1321: when "Word lid" refused a registration — an unknown postal code,
a missing birth date — the page came back with the head of household only. The
container of the extra persons started empty, so everyone else the visitor had
typed was gone, their relation and extra e-mail addresses with them.

Now the refused form renders every person's row again from what was submitted.
A person the visitor removed is not in the submission and does not come back.

Proven red against master `75335a48` (29 September 2026): the refused page had
no `m1_` or `m2_` field at all.
"""

import re

import pytest

from app.domains.mdm.api import RelationType
from tests.conftest import nieuw_lid_velden

pytestmark = pytest.mark.ui_serverrendered

KIND = RelationType.ADULT_CHILD.value
PARTNER = RelationType.PARTNER.value


def _person(n: int, first: str, relation: str) -> dict:
    return {
        f"m{n}_first_name": first,
        f"m{n}_last_name": "Terugkeer",
        f"m{n}_date_of_birth": "2001-02-03",
        f"m{n}_gender_code": "V",
        f"m{n}_relation_type": relation,
    }


def _value(html: str, name: str) -> str | None:
    found = re.search(rf'name="{name}"[^>]*value="([^"]*)"', html)
    return found.group(1) if found else None


def _selected(html: str, name: str) -> str | None:
    select = re.search(rf'<select name="{name}".*?</select>', html, re.S)
    if not select:
        return None
    found = re.search(r'<option value="([A-Z]+)"\s+selected', select.group(0))
    return found.group(1) if found else None


def test_a_refused_registration_keeps_every_person(client, db_session):
    form = {
        **nieuw_lid_velden(db_session, payment_method="transfer", postal_code="9999"),
        **_person(1, "Pieter", PARTNER),
        **_person(2, "Lotte", KIND),
        "m2_email_new_1727000000001": "lotte.extra@example.com",
    }
    page = client.post("/lid-worden", data=form).text

    assert "Nieuw" in page and _value(page, "m0_first_name") == "Nieuw"
    assert _value(page, "m1_first_name") == "Pieter", "person 2 is gone after the refusal"
    assert _value(page, "m2_first_name") == "Lotte", "person 3 is gone after the refusal"
    assert _value(page, "m2_date_of_birth") == "2001-02-03"
    assert _selected(page, "m1_relation_type") == PARTNER
    assert _selected(page, "m2_relation_type") == KIND
    assert _value(page, "m2_email_new_1727000000001") == "lotte.extra@example.com"


def test_a_removed_person_does_not_come_back(client, db_session):
    """Rows 1 and 3 submitted — row 2 was removed in the browser."""
    form = {
        **nieuw_lid_velden(db_session, payment_method="transfer", postal_code="9999"),
        **_person(1, "Pieter", PARTNER),
        **_person(3, "Lotte", KIND),
    }
    page = client.post("/lid-worden", data=form).text

    assert _value(page, "m1_first_name") == "Pieter" and _value(page, "m3_first_name") == "Lotte"
    assert 'name="m2_first_name"' not in page

"""#1321 — "Word lid" prefills partner for person 2 and child after that.

Koen, 29 September 2026: *"Meestal werkt men zo: hoofdlid, partner, kinderen."*
The relation list of every person after the head of household started empty, so
the browser showed its first option, "Partner", for the third and fourth person
too; and the server, receiving no relation, made every extra person a partner. A
family registered without touching the lists came out with several partners.

One rule, `membership.default_relation`: head of household first, then partner as
long as there is none, then child. The form prefills a new row with it — the
relations already on the form travel with "+ Gezinslid toevoegen" — and the server
falls back on it. Only the prefill: two partners chosen by hand stay possible.

Proven red against master `54bc8681` (29 September 2026): the registration without
relations came out as HOOFDLID, PARTNER, PARTNER, and the third row was
prefilled with nothing (the browser's first option, Partner).
"""

import re

import pytest

from app.domains.mdm.api import Person, RelationType
from app.domains.membership.api import default_relation
from tests.conftest import nieuw_lid_velden

pytestmark = pytest.mark.ui_serverrendered

HOOFDLID = RelationType.PRIMARY_MEMBER.value
PARTNER = RelationType.PARTNER.value
KIND = RelationType.ADULT_CHILD.value


@pytest.mark.parametrize(
    "earlier, expected",
    [
        ([], HOOFDLID),
        ([HOOFDLID], PARTNER),
        ([HOOFDLID, PARTNER], KIND),
        ([HOOFDLID, PARTNER, KIND], KIND),
        ([HOOFDLID, KIND], PARTNER),  # no partner yet: the next one is
    ],
)
def test_the_rule(earlier, expected):
    assert default_relation(earlier) == expected


def _selected(html: str) -> str | None:
    found = re.search(r'<option value="([A-Z]+)"\s+selected', html)
    return found.group(1) if found else None


def test_a_new_row_starts_with_the_rules_default(client):
    second = client.get(f"/lid-worden/persoon-rij?index=1&relations={HOOFDLID}").text
    third = client.get(f"/lid-worden/persoon-rij?index=2&relations={HOOFDLID},{PARTNER}").text

    assert _selected(second) == PARTNER, "person 2 is not prefilled as partner"
    assert _selected(third) == KIND, "person 3 is not prefilled as child"


def _person(n: int, last_name: str, relation: str | None) -> dict:
    fields = {
        f"m{n}_first_name": f"Persoon{n}",
        f"m{n}_last_name": last_name,
        f"m{n}_date_of_birth": "2000-01-01",
        f"m{n}_gender_code": "M",
    }
    if relation is not None:
        fields[f"m{n}_relation_type"] = relation
    return fields


def _relations(db, last_name: str) -> list[str]:
    head = db.query(Person).filter_by(last_name=last_name, first_name="Nieuw").one()
    member = head.member_persons[0].member
    links = sorted(member.member_persons, key=lambda mp: mp.person.first_name)
    return [str(mp.relation_type) for mp in links]


def test_a_registration_without_relations_is_head_partner_child(client, db_session):
    name = "Standaardrelatie"
    form = {
        **nieuw_lid_velden(db_session, m0_last_name=name, payment_method="transfer"),
        **_person(1, name, None),
        **_person(2, name, None),
    }
    answer = client.post("/lid-worden", data=form)
    assert answer.status_code == 200, answer.text[:300]
    # "Nieuw" sorts before "Persoon1" and "Persoon2": head, person 2, person 3.
    assert _relations(db_session, name) == [HOOFDLID, PARTNER, KIND]


def test_two_partners_chosen_by_hand_are_accepted(client, db_session):
    name = "Tweepartners"
    form = {
        **nieuw_lid_velden(db_session, m0_last_name=name, payment_method="transfer"),
        **_person(1, name, PARTNER),
        **_person(2, name, PARTNER),
    }
    client.post("/lid-worden", data=form)
    assert _relations(db_session, name) == [HOOFDLID, PARTNER, PARTNER]

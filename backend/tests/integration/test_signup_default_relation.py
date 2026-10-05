"""#1321 — "Word lid" prefills partner for person 2 and child after that.

Koen, 29 September 2026: *"Meestal werkt men zo: hoofdlid, partner, kinderen."*
The relation list of every person after the head of household started empty, so
the browser showed its first option, "Partner", for the third and fourth person
too; and the server, receiving no relation, made every extra person a partner. A
family registered without touching the lists came out with several partners.

One rule, `membership.default_relation`: head of household first, then partner as
long as there is none, then child. The server falls back on it, and the page asks
it: since #1590 a person added on the page is the kit's own row, and the page
asks `GET /lid-worden/relatie?others=<the relations already chosen>` which
relation the rule gives them (until then the relations travelled with the
request for a new row). Only the prefill: two partners chosen by hand stay
possible.

Proven red against master `54bc8681` (29 September 2026): the registration without
relations came out as HOOFDLID, PARTNER, PARTNER, and the third row was
prefilled with nothing (the browser's first option, Partner).
"""

import pytest

from app.domains.mdm.api import Person, RelationType
from app.domains.membership.api import default_relation
from tests.conftest import signup_fields

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


@pytest.mark.parametrize(
    "others, expected",
    [
        ("", PARTNER),  # the main member alone: person 2 is the partner
        (PARTNER, KIND),
        (f"{PARTNER},{KIND}", KIND),
        (KIND, PARTNER),  # a child chosen by hand, no partner yet
    ],
)
def test_the_page_is_told_the_rules_default_for_a_new_row(client, others, expected):
    """The main member is not among `others` — the page sends the relation
    selects, and the first row has none — so the route puts them in front."""
    answer = client.get("/lid-worden/relatie", params={"others": others})
    assert answer.status_code == 200
    assert answer.text == expected


def test_the_page_asks_when_a_row_is_added(client):
    """The wiring on the page itself: a row that is added asks the route, with
    the relation selects as `others`. Whether the answer lands in the select is
    the browser's, and the e2e test's."""
    html = client.get("/lid-worden").text
    assert "/lid-worden/relatie?others=" in html, "the page no longer asks the rule"
    assert 'name="h.__H__.relation_type"' in html, "a new row has no relation to prefill"


def _relations(db, last_name: str) -> list[str]:
    head = db.query(Person).filter_by(last_name=last_name, first_name="Nieuw").one()
    member = head.member_persons[0].member
    links = sorted(member.member_persons, key=lambda mp: mp.person.first_name)
    return [str(mp.relation_type) for mp in links]


def test_a_registration_without_relations_is_head_partner_child(client, db_session):
    name = "Standaardrelatie"
    form = signup_fields(
        db_session, {"last_name": name}, {"last_name": name}, **{"h.n0.last_name": name}
    )
    assert not [field for field in form if field.endswith(".relation_type")], (
        "this form must send no relation at all"
    )
    answer = client.post("/lid-worden", data=form)
    assert answer.status_code == 200, answer.text[:300]
    # "Nieuw" sorts before "Persoon1" and "Persoon2": head, person 2, person 3.
    assert _relations(db_session, name) == [HOOFDLID, PARTNER, KIND]


def test_two_partners_chosen_by_hand_are_accepted(client, db_session):
    name = "Tweepartners"
    form = signup_fields(
        db_session,
        {"last_name": name, "relation_type": PARTNER},
        {"last_name": name, "relation_type": PARTNER},
        **{"h.n0.last_name": name},
    )
    answer = client.post("/lid-worden", data=form)
    assert answer.status_code == 200, answer.text[:300]
    assert _relations(db_session, name) == [HOOFDLID, PARTNER, PARTNER]

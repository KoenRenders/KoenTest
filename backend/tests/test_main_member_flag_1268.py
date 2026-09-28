"""The main member keeps the fields only a main member has (#1268).

CR-12 phase 2 made `relation_type` a `RelationType` member. Two templates still
compared it with the string "HOOFDLID", which a member never equals, so for the
main member both screens rendered as for anyone else:

- the admin household page showed a relation select without the HOOFDLID
  option instead of the hidden `relation_type=HOOFDLID` field. The server does
  not demote a main member (`membership/service.py`), but the screen offered it;
- the family portal dropped the hidden field and no longer marked mobile as
  required for the main member. (E-mail is not in that field set on the portal
  since #1219: the addresses are rows of their own.)

The two comparisons sat on the template ratchet as "not cleaned up yet", and
the ratchet stayed green while they broke. The view models now carry
`is_main_member`, and the templates read that.

Broken on purpose (27 September 2026): both templates set back to
`p.relation_type == "HOOFDLID"` → the admin and the portal test failed, each
on its lost hidden HOOFDLID field; the partner test stayed green, as it should.
"""

import re

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family

HIDDEN = 'name="relation_type" value="HOOFDLID"'


def test_the_admin_form_keeps_the_main_member_a_main_member(client, db_session):
    member, person = create_test_family(db_session, email="main-1268@example.org")
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    html = client.get(f"/admin/leden/gezin/{member.id}").text
    assert f'id="lp{person.id}-first_name"' in html, "the person's edit fields are not on the page"
    assert HIDDEN in html, "the main member's form lost its hidden HOOFDLID field"
    assert f'id="lp{person.id}-relation_type"' not in html, (
        "the main member is offered a relation select, as if it could stop being the main member"
    )


def test_the_portal_keeps_the_main_member_fields(client, db_session):
    member, person = create_test_family(db_session, email="main-1268-portal@example.org")
    client.cookies.set(SESSION_COOKIE, make_session_value("main-1268-portal@example.org"))
    html = client.get("/leden/gezin").text
    assert f'id="p{person.id}-first_name"' in html, "the person's edit fields are not on the page"
    assert HIDDEN in html, "the portal form lost the main member's hidden HOOFDLID field"
    assert re.search(rf'id="p{person.id}-mobile"[^>]*required', html), (
        "mobile is no longer required for the main member"
    )


def test_a_partner_is_not_a_main_member(client, db_session):
    """The other half: without it, a template that always said "main member"
    would pass the two tests above."""
    member, person = create_test_family(
        db_session, email="partner-1268@example.org", relation_type="PARTNER"
    )
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    html = client.get(f"/admin/leden/gezin/{member.id}").text
    assert f'id="lp{person.id}-first_name"' in html, "the person's edit fields are not on the page"
    assert HIDDEN not in html
    assert f'id="lp{person.id}-relation_type"' in html

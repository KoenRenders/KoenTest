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

Since #1590 the portal is the public form page with the household as a group of
rows. It has no relation field at all — the save leaves a stored person's
relation alone. What the portal shows of "this is the main member" is the
row's title — the relation's label before the name, which `household_page`
reads from the same `relation_type` member — and, in the edit mode, the
required Gsm field: the main member's and nobody else's. A comparison that no
longer matches the member gives an empty prefix and no required field, for
everyone.

The two comparisons sat on the template ratchet as "not cleaned up yet", and
the ratchet stayed green while they broke. The view models now carry
`is_main_member`, and the templates read that.

Broken on purpose (27 September 2026): both templates set back to
`p.relation_type == "HOOFDLID"` → the admin and the portal test failed, each
on its lost hidden HOOFDLID field; the partner test stayed green, as it should.
"""

import re

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family, household_fields

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


def _row_titles(html: str) -> list[tuple[str, str]]:
    """(relation label, name) of every person row on the portal."""
    return re.findall(
        r"<span data-row-title-prefix>([^<]*)</span>.*?<h3 data-row-title=\"([^\"]*)\"", html, re.S
    )


def test_the_portal_shows_the_main_member_as_the_main_member(client, db_session):
    """Two persons, so the label follows the relation and not the row: the main
    member reads "Hoofdlid", and the person the member adds through the portal —
    who joins as a child — reads as one."""
    member, person = create_test_family(
        db_session, email="main-1268-portal@example.org", mobile="0470 00 00 01"
    )
    db_session.commit()
    session = make_session_value("main-1268-portal@example.org")
    client.cookies.set(SESSION_COOKIE, session)
    fields = household_fields(client)
    fields["h_order"] = [*fields["h_order"], "n1"]
    fields.update(
        {
            "h.n1.first_name": "Tweede",
            "h.n1.last_name": "Persoon",
            "h.n1.date_of_birth": "2012-03-04",
            "h.n1.gender_code": "F",
        }
    )
    saved = client.post(
        "/leden/gezin", data=fields, headers={"X-CSRF-Token": csrf_token_for(session)}
    )
    assert saved.status_code == 200, saved.text[:300]

    for page in ("/leden/gezin", "/leden/gezin?bewerken=1"):
        html = client.get(page).text
        stored = [t for t in _row_titles(html) if t[1] != "Nieuw gezinslid"]
        assert stored == [
            ("Hoofdlid", "Test Persoon"),
            ("(meerderjarig) kind", "Tweede Persoon"),
        ], page
    # The edit mode asks no relation of a stored person: it cannot be changed here.
    assert f'name="h.{person.id}.first_name"' in html, (
        "the person's edit fields are not on the page"
    )
    assert f'name="h.{person.id}.relation_type"' not in html
    # Mobile is required for the main member, and for the main member only.
    required = set(re.findall(r'id="h-(\d+)-mobile" name="h\.\d+\.mobile" required', html))
    asked = set(re.findall(r'id="h-(\d+)-mobile"', html))
    assert len(asked) == 2, "the two persons' Gsm fields are not both on the page"
    assert required == {str(person.id)}


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

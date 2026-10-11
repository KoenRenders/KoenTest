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


def test_the_admin_form_keeps_the_main_member_a_main_member(client, db_session):
    """#1899: the main member's card carries the fixed badge and no relation
    select, and its form sends no relation — the one save leaves his place alone."""
    from tests.conftest import record_fields

    member, person = create_test_family(db_session, email="main-1268@example.org")
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    html = client.get(f"/admin/leden/gezin/{member.id}?bewerken=1").text
    assert f'id="h-{person.id}-first_name"' in html, "the person's edit fields are not on the page"
    card = html[html.index('id="hoofdlid"') :]
    card = card[: card.index("data-form-grid")]
    assert ">Hoofdlid</span>" in card, "the main member's card lost its badge"
    assert f'id="h-{person.id}-relation_type"' not in html, (
        "the main member is offered a relation select, as if it could stop being the main member"
    )
    assert f"h.{person.id}.relation_type" not in record_fields(client, member.id)


def _row_titles(html: str) -> list[tuple[str, str]]:
    """(relation label, name) of every person card on the portal that is no main
    member (#1899: the name is the card's heading, the relation its badge when
    the page is read and the chosen option of its select when it is edited)."""
    cards = []
    for name, relation in re.findall(
        r"<h2 data-person-name[^>]*>([^<]*)</h2>\s*<span data-person-relation[^>]*>.*?>([^<>]+)</span>",
        html,
        re.S,
    ):
        cards.append((relation.strip(), name.strip()))
    # Editing: per card its own title line — a card without a select (the main
    # member's) must not borrow the next card's.
    for card in html.split("<div data-row-title-line")[1:]:
        # The title line ends where the card's fields begin.
        line = card.split("data-form-grid")[0]
        name = re.search(r"<h3 data-row-title=\"([^\"]*)\"", line)
        select = re.search(
            r"<select[^>]*name=\"h\.\w+\.relation_type\"[^>]*>(.*?)</select>", line, re.S
        )
        if not (name and select):
            continue
        chosen = re.search(r"<option[^>]* selected[^>]*>([^<]*)</option>", select.group(1))
        cards.append((chosen.group(1).strip() if chosen else "", name.group(1)))
    return [card for card in cards if card[0] != "Hoofdlid"]


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
            # #1603: the member chooses; without a choice this first added person
            # would be the partner.
            "h.n1.relation_type": "KIND",
        }
    )
    saved = client.post(
        "/leden/gezin", data=fields, headers={"X-CSRF-Token": csrf_token_for(session)}
    )
    assert saved.status_code == 200, saved.text[:300]

    for page in ("/leden/gezin", "/leden/gezin?bewerken=1"):
        html = client.get(page).text
        stored = [t for t in _row_titles(html) if t[1] != "Nieuw gezinslid"]
        # #1632, #1899: the main member is no row of the group but the first
        # card, with the badge "Hoofdlid"; the others follow.
        assert stored == [("(meerderjarig) kind", "Tweede Persoon")], page
        head = html[html.index('id="hoofdlid"') : html.index('id="gezin-adres"')]
        assert ">Hoofdlid</span>" in head and "Tweede" not in head, page
    # #1899 (Koen, 11 October 2026): the edit mode asks the relation of every
    # person but the main member, whose card carries the fixed badge.
    assert f'name="h.{person.id}.first_name"' in html, (
        "the person's edit fields are not on the page"
    )
    assert f'name="h.{person.id}.relation_type"' not in html
    assert len(re.findall(r'<select[^>]*name="h\.\d+\.relation_type"', html)) == 1
    # #1603: Mijn gezin asks nobody's mobile number — also not the main member's.
    required = set(re.findall(r'id="h-(\d+)-mobile" name="h\.\d+\.mobile" required', html))
    asked = set(re.findall(r'id="h-(\d+)-mobile"', html))
    assert len(asked) == 2, "the two persons' Gsm fields are not both on the page"
    assert required == set()
    # Word lid still does, of the main member and of nobody added in the page.
    client.cookies.clear()
    signup = client.get("/lid-worden").text
    assert re.search(r'id="h-n0-mobile" name="h\.n0\.mobile" required', signup)
    assert not re.search(r'name="h\.__H__\.mobile" required', signup)
    assert 'name="h.__H__.mobile"' in signup, "the template row is not on the page"


def test_a_partner_is_not_a_main_member(client, db_session):
    """The other half: without it, a template that always said "main member"
    would pass the test above. A household whose only person is a partner shows
    that person first, with the relation it has — not as the main member."""
    member, person = create_test_family(
        db_session, email="partner-1268@example.org", relation_type="PARTNER"
    )
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    html = client.get(f"/admin/leden/gezin/{member.id}?bewerken=1").text
    assert f'id="h-{person.id}-first_name"' in html, "the person's edit fields are not on the page"
    card = html[html.index('id="hoofdlid"') :]
    card = card[: card.index("data-form-grid")]
    assert "partner" in card.lower() and "Hoofdlid" not in card

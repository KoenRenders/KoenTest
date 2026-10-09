"""#1780 — the newsletter's send screen says who it sends to, before the click.

Koen, 8 October 2026: the screen read "Leden · 22 adressen" and the button
"Verstuur naar 22 abonnees". Nothing said who "Leden" are — everyone who was
ever a member? — and the button called members subscribers.

The first card now names each list the letter goes to: the members of the
working year with their addresses and households, the subscribers, and for both
what the lists share. The button says "leden" for members, "abonnees" only for
subscribers, "ontvangers" for both. Who gets the letter does not change.

Red (each restored after): the button's words taken from the subscribers' branch
for every audience → the members test reads "abonnees"; the households counted
as every household with a membership instead of those the addresses came from
→ "in 3 gezinnen" (the world holds a member household nobody can mail); the
member line left out for "both" → one line where two are asked.
"""

from __future__ import annotations

import re
from datetime import date
from html import unescape

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person
from app.domains.membership.api import Membership
from app.domains.newsletter import service as nb
from app.domains.newsletter.api import Audience
from app.domains.newsletter.models import Newsletter, Subscriber, SubscriberStatus
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

YEAR = date.today().year
MEMBERS_SENTENCE = (
    "Elk e-mailadres van elke persoon in een gezin met een lidmaatschap voor dit werkjaar: "
    "3 adressen in 2 gezinnen. Oud-leden en gezinnen zonder lidmaatschap dit jaar krijgen hem niet."
)
SUBSCRIBERS_SENTENCE = "Iedereen die zich inschreef op de nieuwsbrief en dat bevestigde."


def _household(db, *addresses, year=YEAR):
    member = Member()
    db.add(member)
    db.flush()
    for n, address in enumerate(addresses):
        person = Person(
            date_of_birth=date(1980, 1, 1), gender_code="M", first_name=f"P{n}", last_name="Proef"
        )
        db.add(person)
        db.flush()
        relation = "HOOFDLID" if n == 0 else "PARTNER"
        db.add(MemberPerson(member_id=member.id, person_id=person.id, relation_type=relation))
        if address:
            db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=address))
    if year is not None:
        db.add(
            Membership(
                member_id=member.id,
                year=year,
                is_active=True,
                valid_from=date(year, 1, 1),
                valid_to=date(year, 12, 31),
            )
        )
    db.flush()


@pytest.fixture
def world(db_session):
    """Two households with a membership this year that can be mailed (three
    addresses) and one that cannot (nobody in it has an address), one former
    member, and two subscribers of whom one is also a member."""
    _household(db_session, "lid-a@example.com", "lid-b@example.com")
    _household(db_session, "lid-c@example.com")
    _household(db_session, None)
    _household(db_session, "oud-lid@example.com", year=YEAR - 2)
    for address in ("abonnee@example.com", "lid-c@example.com"):
        db_session.add(
            Subscriber(
                email=address,
                status=SubscriberStatus.CONFIRMED,
                source="admin",
                unsubscribe_token=f"tok-{address}",
            )
        )
    db_session.commit()


def _screen(client, db, audience: Audience) -> str:
    letter = Newsletter(subject="Proef", body_html="<div>Beste</div>", audience=audience)
    db.add(letter)
    db.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    answer = client.get(f"/admin/nieuwsbrieven/{letter.id}/versturen")
    assert answer.status_code == 200, answer.text[:300]
    return answer.text


def _card(html: str) -> tuple[list[tuple[str, str]], list[str]]:
    lines = re.findall(
        r"<div data-audience-line>\s*<p[^>]*><strong>(.*?)</strong></p>\s*<p[^>]*>(.*?)</p>",
        html,
        re.S,
    )
    overlap = re.findall(r"<p[^>]*data-audience-overlap[^>]*>(.*?)</p>", html, re.S)
    return [(unescape(h).strip(), unescape(s).strip()) for h, s in lines], [
        unescape(o).strip() for o in overlap
    ]


def _button(html: str) -> str:
    found = re.findall(r'<button[^>]*type="submit"[^>]*>(.*?)</button>', html, re.S)
    words = [re.sub(r"<[^>]+>", "", unescape(b)).strip() for b in found]
    return next(w for w in words if w.startswith("Verstuur naar"))


def test_members_are_named_with_the_year_the_addresses_and_the_households(
    client, db_session, world
):
    html = _screen(client, db_session, Audience.MEMBERS)
    lines, overlap = _card(html)

    assert lines == [(f"Leden van werkjaar {YEAR} · 3 adressen", MEMBERS_SENTENCE)]
    assert overlap == []
    assert _button(html) == "Verstuur naar 3 leden"
    assert "abonnee" not in _button(html), "members are no subscribers"
    assert html.count(MEMBERS_SENTENCE) == 1 and "oud-lid@example.com" not in html


def test_subscribers_are_called_subscribers(client, db_session, world):
    html = _screen(client, db_session, Audience.NON_MEMBERS)
    lines, overlap = _card(html)

    assert lines == [("Abonnees · 2 adressen", SUBSCRIBERS_SENTENCE)]
    assert overlap == []
    assert _button(html) == "Verstuur naar 2 abonnees"
    assert "Leden van werkjaar" not in html


def test_both_names_the_two_lists_and_what_they_share(client, db_session, world):
    html = _screen(client, db_session, Audience.BOTH)
    lines, overlap = _card(html)

    assert lines == [
        (f"Leden van werkjaar {YEAR} · 3 adressen", MEMBERS_SENTENCE),
        ("Abonnees · 2 adressen", SUBSCRIBERS_SENTENCE),
    ]
    assert overlap == ["1 adres staat op beide lijsten en krijgt hem één keer, als lid."]
    assert _button(html) == "Verstuur naar 4 ontvangers"


@pytest.mark.parametrize("audience", list(Audience))
def test_the_numbers_are_those_of_the_list_that_is_sent(db_session, world, audience):
    """The summary and the recipient list come from the same calls: what the
    screen counts is what leaves."""
    said = nb.audience_summary(db_session, audience)
    recipients = nb.recipients_for(db_session, audience)

    assert said.recipients == len(recipients)
    year, households, addresses = nb.member_audience(db_session)
    if audience is not Audience.NON_MEMBERS:
        assert (said.year, said.households, said.member_addresses) == (year, len(households), 3)
        assert len(households) == 2 and sorted(addresses) == [
            "lid-a@example.com",
            "lid-b@example.com",
            "lid-c@example.com",
        ]
    else:
        assert (said.households, said.member_addresses) == (0, 0)

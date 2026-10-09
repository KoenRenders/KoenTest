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

#1834 — the concept screen, where the audience is chosen, says the same: who
each list is and what the two share, in the send screen's words and from the
same function, and the second list is called "Abonnees" there too (it read
"Niet-leden", with who that is in a hover text). Red (each restored after): the
partial taken out of the concept screen → no line there; the subscribers'
sentence given a wording of its own for one audience → the two screens no longer
say the same; `value = :old` taken out of the migration's UPDATE → a word
somebody else put there is overwritten. Not a red proof, and said so: putting
the seed's word in `newsletter/codes.py` back to "Niet-leden" leaves these tests
green, because the test database is built by the migrations and the last one
rewords the label whatever the seed says — the migration is what carries the
word, the seed only keeps a fresh database from saying the old word in between.
"""

from __future__ import annotations

import importlib.util
import re
from datetime import date
from html import unescape
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.mdm.api import ContactDetail, Member, MemberPerson, Person
from app.domains.membership.api import Membership
from app.domains.newsletter import service as nb
from app.domains.newsletter.api import Audience
from app.domains.newsletter.models import Newsletter, Subscriber, SubscriberStatus
from app.kernel.codes import code_label
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


# ── #1834: the concept screen says it too, in the same words ──────────────────

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "200_2026_10_09_060229_the_newsletter_s_second_audience_is_.py"
)


def _concept(client, db, audience: Audience | None = None) -> str:
    letter = Newsletter(subject="Proef", body_html="<div>Beste</div>", audience=audience)
    db.add(letter)
    db.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    answer = client.get(f"/admin/nieuwsbrieven/{letter.id}")
    assert answer.status_code == 200, answer.text[:300]
    return answer.text


def _pills(html: str) -> list[tuple[str, str, str]]:
    """`(code, word, number)` of each choice, and no hover text on any of them."""
    labels = re.findall(
        r"<label([^>]*)>\s*<input type=\"radio\" name=\"audience\"(.*?)</label>", html, re.S
    )
    assert labels, "the concept screen offers no audience"
    assert not [attrs for attrs, _rest in labels if "title=" in attrs], "a hover text is back"
    found = []
    for _attrs, rest in labels:
        code = re.search(r'value="([^"]*)"', rest).group(1)
        word, number = re.findall(r"<span[^>]*>(.*?)</span>", rest, re.S)
        found.append((code, unescape(word).strip(), unescape(number).strip()))
    return found


def test_the_concept_screen_says_who_each_audience_is_before_a_choice(client, db_session, world):
    html = _concept(client, db_session)
    lines, overlap = _card(html)

    assert _pills(html) == [
        ("members", "Leden", "3"),
        ("non_members", "Abonnees", "2"),
        ("both", "Allebei", "4"),
    ]
    assert lines == [
        (f"Leden van werkjaar {YEAR} · 3 adressen", MEMBERS_SENTENCE),
        ("Abonnees · 2 adressen", SUBSCRIBERS_SENTENCE),
    ]
    assert overlap == ["1 adres staat op beide lijsten en krijgt hem één keer, als lid."]
    assert "Niet-leden" not in html and "niet-leden" not in html


@pytest.mark.parametrize("audience", list(Audience))
def test_the_two_screens_say_the_same_of_the_same_audience(client, db_session, world, audience):
    """Every line and the overlap of the send screen stand on the concept screen,
    word for word: one function words both, and this fails when one of the two
    gets a wording of its own."""
    send_lines, send_overlap = _card(_screen(client, db_session, audience))
    concept_lines, concept_overlap = _card(_concept(client, db_session, audience))

    assert send_lines, "the send screen names no list"
    for line in send_lines:
        assert line in concept_lines, f"the concept screen does not say: {line}"
    for sentence in send_overlap:
        assert sentence in concept_overlap


def test_the_list_of_letters_calls_the_second_audience_abonnees(client, db_session, world):
    _concept(client, db_session, Audience.NON_MEMBERS)
    html = client.get("/admin/nieuwsbrieven").text

    assert code_label("audience", "non_members", language="nl", db=db_session) == "Abonnees"
    assert code_label("audience", "non_members", language="en", db=db_session) == "Subscribers"
    assert "Abonnees" in html and "Niet-leden" not in html


def _label(db, language: str) -> str:
    return db.execute(
        text(
            "SELECT value FROM newsletter.audience_labels "
            "WHERE code = 'non_members' AND language = :language"
        ),
        {"language": language},
    ).scalar_one()


def _set_label(db, language: str, value: str) -> None:
    db.execute(
        text(
            "UPDATE newsletter.audience_labels SET value = :value "
            "WHERE code = 'non_members' AND language = :language"
        ),
        {"language": language, "value": value},
    )


def test_the_migration_rewords_the_old_word_and_nothing_else(db_session):
    """An environment carries the word a migration seeded; the migration replaces
    it — twice without harm, and not a word somebody else put there."""
    spec = importlib.util.spec_from_file_location("migration_audience_word", MIGRATION)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    bind = db_session.connection()
    _set_label(db_session, "nl", "Niet-leden")
    _set_label(db_session, "en", "Sympathisers")

    migration.reword(bind, 0, 1)
    migration.reword(bind, 0, 1)

    assert _label(db_session, "nl") == "Abonnees"
    assert _label(db_session, "en") == "Sympathisers", "a word of somebody else was overwritten"

    migration.reword(bind, 1, 0)
    assert _label(db_session, "nl") == "Niet-leden", "the downgrade does not restore the word"
    db_session.rollback()

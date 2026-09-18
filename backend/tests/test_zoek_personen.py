"""One person search for every caller (#1006).

The search lived in the meeting-circle SCREEN, with a note that a search
argument on `mdm` would be "a second contract for one caller". CR-10's organiser
picker is the second caller, so it moved to `mdm.api` instead of being copied —
two searches drifting apart is the pattern CLAUDE.md warns about.

The circle test is the one that matters: the circle holds people who are NOT
members (the department's support worker, #939). It goes through the circle
ROUTE, so it turns red if someone later limits the circle to members.

Broken to see them red (measured):
- `members_only` ignored in `search_persons` → the members-only test fails;
- the escaping of LIKE characters removed → the special-character test fails
  (`%` then matches everyone);
- `exclude_ids` ignored → that test fails.

Measured and NOT red: dropping the id tiebreaker from the sort. Postgres then
still returns the two namesakes in insertion order here, so this data cannot
prove it. The assertion stays because it pins the intended order (#761) — it is
a promise, not a proof.
"""
import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Member, MemberPerson, Person, search_persons
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _person(db, voornaam, achternaam, *, lid=False):
    person = Person(first_name=voornaam, last_name=achternaam)
    db.add(person)
    db.flush()
    if lid:
        gezin = Member()
        db.add(gezin)
        db.flush()
        db.add(MemberPerson(member_id=gezin.id, person_id=person.id,
                            relation_type="HOOFDLID"))
        db.flush()
    return person


@pytest.fixture
def mensen(db_session):
    return {
        "jan": _person(db_session, "Jan", "Peeters", lid=True),
        "marjan": _person(db_session, "Marjan", "Vermeir", lid=True),
        "piet": _person(db_session, "Piet", "Claes", lid=True),
        "helper": _person(db_session, "Jana", "Ondersteuner"),  # geen gezin
    }


def _namen(rijen):
    return [f"{p.first_name} {p.last_name}" for p in rijen]


# ── De zoekfunctie zelf ──────────────────────────────────────────────────────

def test_a_query_matches_first_and_last_name_anywhere(db_session, mensen):
    gevonden = _namen(search_persons(db_session, "jan"))

    assert "Jan Peeters" in gevonden
    assert "Marjan Vermeir" in gevonden, "een treffer midden in de voornaam telt ook"
    assert "Piet Claes" not in gevonden


def test_the_order_is_deterministic(db_session, mensen):
    eerste = _person(db_session, "Anna", "Zelfde")
    tweede = _person(db_session, "Anna", "Zelfde")

    gevonden = search_persons(db_session, "anna zelfde")
    assert [p.id for p in gevonden] == sorted([eerste.id, tweede.id]), (
        "twee naamgenoten kwamen in een andere volgorde dan op id terug")


def test_members_only_leaves_out_who_is_in_no_household(db_session, mensen):
    assert "Jana Ondersteuner" in _namen(search_persons(db_session, "jan"))
    assert "Jana Ondersteuner" not in _namen(
        search_persons(db_session, "jan", members_only=True))
    assert "Jan Peeters" in _namen(search_persons(db_session, "jan", members_only=True))


def test_exclude_ids_and_limit(db_session, mensen):
    zonder = _namen(search_persons(db_session, "jan",
                                   exclude_ids=[mensen["jan"].id]))
    assert "Jan Peeters" not in zonder and "Marjan Vermeir" in zonder

    for i in range(20):
        _person(db_session, f"Janneke{i}", "Veel")
    assert len(search_persons(db_session, "jan")) == 15
    assert len(search_persons(db_session, "jan", limit=3)) == 3


def test_an_empty_query_finds_nobody(db_session, mensen):
    assert search_persons(db_session, "") == []
    assert search_persons(db_session, "   ") == []


def test_a_like_character_is_searched_for_and_not_interpreted(db_session, mensen):
    _person(db_session, "Jo", "100% Zeker")

    assert _namen(search_persons(db_session, "%")) == ["Jo 100% Zeker"], (
        "'%' werkte als jokerteken; dan komt iedereen terug")
    assert _namen(search_persons(db_session, "_")) == [], "'_' matchte elk teken"


# ── Via de route van de vergaderkring ────────────────────────────────────────

def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _kring(client, q):
    resp = client.get("/admin/vergaderingen/kring", params={"q": q},
                      headers={"HX-Request": "true"})
    assert resp.status_code == 200
    return resp.text


def test_the_circle_still_finds_someone_who_is_not_a_member(client, db_session, mensen):
    """The point of the circle (#939): the support worker is in no household.

    Through the route, so limiting the circle to members later turns this red.
    """
    _login(client)
    html = _kring(client, "jan")

    assert "Ondersteuner" in html, "de kring vindt geen niet-lid meer"
    assert "Peeters" in html, "en een lid evengoed"


def test_the_circle_and_the_search_answer_the_same(client, db_session, mensen):
    """Not a grep for the old loop: both paths are asked the same question.

    A special character is the sharpest question — the screen's Python `in` and
    a SQL LIKE differ exactly there.
    """
    _person(db_session, "Jo", "100% Zeker")
    _login(client)

    for vraag in ("jan", "%", "_", "zeker"):
        via_functie = _namen(search_persons(db_session, vraag))
        html = _kring(client, vraag)
        for naam in via_functie:
            assert naam.split()[-1] in html, (vraag, naam)
        for weg in set(_namen(search_persons(db_session, ""))) - set(via_functie):
            assert weg not in html, (vraag, weg)

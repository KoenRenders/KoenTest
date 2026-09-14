"""The masking gates: what a name does on its way to Mistral (#917, CR-07 §5).

Three channels carry a name out of this building, and each has its own mechanism:
what the database returns (tokenised), what the admin types (scrubbed), and
whatever slips past both (blocked at the seam). The change request asks for one
gate per mechanism, and for each of them to be proven by breaking it.

The shape of every test here is the same, and it is the shape that matters: seed a
name into the administration, drive the real path, and assert the name is not in
the payload the provider was handed. Not "the tokenisation ran" — that is a claim
about the code. The payload is the evidence.
"""
import json
import re

import pytest

from app.domains.chatbot.providers.base import AssistantMessage
from app.domains.reporting.assistant import (
    AMBIGUOUS, detokenise, dispatcher, scrub_question,
)

TENANT = 2
ACHTERNAAM = "Vandenbulcke"


def _household(db, first: str, last: str, *, board_member=None, extra=0,
               lid=False):
    from app.domains.mdm.api import (
        Address, Member, MemberPerson, Person, PostalCode,
    )

    postal = db.query(PostalCode).filter(PostalCode.postal_code == "2400").first()
    if postal is None:
        postal = PostalCode(postal_code="2400", municipality="Mol")
        db.add(postal)
        db.flush()
    member = Member(tenant_id=TENANT,
                    board_member_id=board_member.id if board_member else None)
    db.add(member)
    db.flush()
    person = Person(tenant_id=TENANT, first_name=first, last_name=last)
    db.add(person)
    db.flush()
    db.add(MemberPerson(tenant_id=TENANT, member_id=member.id,
                        person_id=person.id, relation_type="HOOFDLID"))
    db.add(Address(tenant_id=TENANT, person_id=person.id, street="Kerkstraat",
                   house_number="7", postal_code_id=postal.id))
    if lid:
        from datetime import date

        from app.domains.membership.api import Membership

        jaar = date.today().year
        db.add(Membership(tenant_id=TENANT, member_id=member.id, year=jaar,
                          valid_from=date(jaar, 1, 1), valid_to=date(jaar, 12, 31),
                          is_active=True))
    for i in range(extra):
        huisgenoot = Person(tenant_id=TENANT, first_name=f"Kind{i}", last_name=last)
        db.add(huisgenoot)
        db.flush()
        db.add(MemberPerson(tenant_id=TENANT, member_id=member.id,
                            person_id=huisgenoot.id, relation_type="KIND"))
    db.flush()
    return member, person


def _all_tokenised_objects():
    from app.domains.reporting.universe import AiExposure, OBJECTS

    objecten = [o for o in OBJECTS if o.ai_exposure is AiExposure.TOKENISED]
    assert len(objecten) >= 7, (
        "deze poort draait over élk object dat een persoon aanwijst; vindt ze er "
        "bijna geen, dan is de classificatie stuk en bewijst de poort niets (#678)"
    )
    return objecten


# ── Channel 1: what the database returns ─────────────────────────────────────

def test_no_person_naming_object_hands_back_a_name(db_session):
    """Every `admin_tokenised` object, run for real, gives a token.

    All of them in one test and not a chosen example: a mechanism that covers six
    of seven objects is the kind that reads as finished. The measure alongside is
    there because a selection without one is refused — the point is the dimension.

    Broken to see it red: `_tokenise_rows` returning its rows unchanged. The
    seeded surname then appears in the result of `member_head_name`, and the
    failure names the object it came from.
    """
    _household(db_session, "Mira", ACHTERNAAM)
    dispatch = dispatcher(tenant_id=TENANT)

    for obj in _all_tokenised_objects():
        maat = ("member_total_count" if obj.klass == "Leden"
                else "registration_count")
        out = json.loads(dispatch("run_report",
                                  {"objects": [obj.key, maat]}, db_session))
        tekst = json.dumps(out, ensure_ascii=False)
        assert ACHTERNAAM not in tekst, f"{obj.key} gaf een naam terug: {tekst[:200]}"
        assert "Kerkstraat" not in tekst, f"{obj.key} gaf een adres terug"
        if out.get("rows"):
            waarden = {str(r.get(obj.key)) for r in out["rows"]}
            assert any(w.startswith(obj.token_prefix + "-") or w in ("onbekend",)
                       or w.startswith("Samengevoegd")
                       for w in waarden), f"{obj.key}: {waarden}"


def test_the_threshold_reaches_a_household_row_before_the_token_does(db_session):
    """Two mechanisms in the same result, and the order is worth knowing.

    A row per household is a group of one family, which is under five people, so
    the small-cell threshold merges it away before the tokenisation has anything to
    do. The token is not the thing protecting these rows — the threshold is — and
    that is why CR-07 §5.5 keeps both: the threshold covers grouped answers, the
    token covers the rows the threshold does not guard (a board member with
    twenty households, a fact that cannot count people).

    Measured rather than assumed: this test was first written expecting a token
    and found `Samengevoegd`.
    """
    from app.domains.reporting.api import MERGED_LABEL

    _household(db_session, "Mira", ACHTERNAAM)
    out = json.loads(dispatcher(tenant_id=TENANT)(
        "run_report", {"objects": ["member", "member_total_count"]}, db_session))
    assert [r["member"] for r in out["rows"]] == [MERGED_LABEL]
    assert "threshold_applied" in out


def test_the_same_household_keeps_the_same_token(db_session):
    """Stable, and stateless — the two are the same property (CR-07 §5.2).

    The id is IN the token, so nothing about the mapping is stored per
    conversation: the household is `gezin-23` in the first turn, in the tenth, and
    after a restart. That is what lets the model notice that two rows are about
    one family without ever learning which family.

    Over the memberships fact, where "people" means people: five in this household,
    so the row stands. On the households fact a "person" is a household, so any
    row there is a group of one and the threshold merges it first — see the test
    above.
    """
    member, _ = _household(db_session, "Mira", ACHTERNAAM, extra=4, lid=True)
    dispatch = dispatcher(tenant_id=TENANT)
    eerst = json.loads(dispatch("run_report",
                                {"objects": ["member", "membership_persons"]},
                                db_session))
    daarna = json.loads(dispatch("run_report",
                                 {"objects": ["member_head_name",
                                              "membership_persons"]},
                                 db_session))
    token = f"gezin-{member.id}"
    assert any(r.get("member") == token for r in eerst["rows"])
    assert any(r.get("member_head_name") == token for r in daarna["rows"])


def test_a_token_resolves_back_to_the_name_for_the_admin_only(db_session):
    """Inbound re-translation (CR-07 §5.3): the admin reads a name, Mistral did not.

    And the lookup is tenant-scoped, which is not decoration: the id comes out of a
    model's output, so it is the one number in this mechanism that a planted
    instruction could try to choose. A token pointing somewhere else finds nothing
    and stays a token rather than becoming a name from another tenant.
    """
    member, _ = _household(db_session, "Mira", ACHTERNAAM)
    zin = f"Het gezin gezin-{member.id} betaalde nog niet."
    assert ACHTERNAAM in detokenise(db_session, zin, tenant_id=TENANT)
    assert ACHTERNAAM not in detokenise(db_session, zin, tenant_id=3)
    assert f"gezin-{member.id}" in detokenise(db_session, zin, tenant_id=3)


def test_a_token_nobody_mentioned_costs_nothing(db_session):
    """Only what is in the text is looked up — no work per household."""
    _household(db_session, "Mira", ACHTERNAAM)
    assert detokenise(db_session, "Er zijn 12 gezinnen.",
                      tenant_id=TENANT) == "Er zijn 12 gezinnen."


# ── Channel 2: what the admin types ──────────────────────────────────────────

def test_a_name_typed_in_the_question_leaves_as_a_token(db_session):
    """The channel that tokenising the database says nothing about (§5.6).

    Broken to see it red: `scrub_question` returning its input. The surname then
    stands in the message that goes out, and this test catches it before the seam
    guard has to.
    """
    member, _ = _household(db_session, "Mira", ACHTERNAAM)
    schoon = scrub_question(db_session, f"Stopt het gezin {ACHTERNAAM} dit jaar?",
                            tenant_id=TENANT)
    assert ACHTERNAAM not in schoon
    assert f"gezin-{member.id}" in schoon


def test_a_name_that_means_two_households_is_removed_and_not_guessed(db_session):
    """The honest half of the trade (CR-07 §5.6).

    A surname is rarely one household. Picking one would answer about the wrong
    family while looking exactly as confident; leaving the name in would send it.
    So it goes out as `[naam]`, and the catalogue tells the model to ask which
    household is meant.
    """
    _household(db_session, "Mira", ACHTERNAAM)
    _household(db_session, "Joris", ACHTERNAAM)
    schoon = scrub_question(db_session, f"Wat betaalde {ACHTERNAAM}?",
                            tenant_id=TENANT)
    assert ACHTERNAAM not in schoon
    assert AMBIGUOUS in schoon


def test_the_scrub_leaves_ordinary_words_alone(db_session):
    """A guard that mangles every question gets switched off.

    Short parts are not matched at all, and a word that is nobody's name passes
    untouched. Without this the mechanism would be technically correct and
    practically unusable — which is the same as absent.
    """
    _household(db_session, "Mira", ACHTERNAAM)
    vraag = "Hoeveel gezinnen per gemeente, en wat staat er open aan lidgeld?"
    assert scrub_question(db_session, vraag, tenant_id=TENANT) == vraag


def test_the_scrub_is_case_insensitive(db_session):
    """Nobody types a name the way the database spells it."""
    member, _ = _household(db_session, "Mira", ACHTERNAAM)
    schoon = scrub_question(db_session, f"en {ACHTERNAAM.upper()}?",
                            tenant_id=TENANT)
    assert ACHTERNAAM.upper() not in schoon
    assert f"gezin-{member.id}" in schoon


# ── Channel 3: whatever slips past both ──────────────────────────────────────

def test_the_whole_path_hands_the_provider_no_name(db_session, client,
                                                   monkeypatch):
    """End to end, through the screen, with the payload as the evidence.

    This is the gate CR-07 §5 asks for in as many words: compose a selection
    containing person-naming objects, capture the exact payload handed to the
    provider, and assert that nothing from the seeded name and address set appears
    in it. Everything before this test checks one mechanism; this one checks that
    they add up on the real path, which is where a mechanism that works alone
    still fails.
    """
    from app.config import settings
    from app.domains.auth.api import (
        SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value,
    )
    from app.kernel.tenant_config import set_setting

    _household(db_session, "Mira", ACHTERNAAM)
    monkeypatch.setattr(settings, "admin_chat_enabled", True)
    monkeypatch.setattr(settings, "chat_llm_provider", "mock")
    set_setting(db_session, "admin_chat_enabled", "1", tenant_id=TENANT)
    db_session.flush()

    email = "masking-beheer@example.com"
    user = User(email=email, is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db_session.flush()
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)

    resp = client.post("/admin/rapporten/raakje", data={
        "vraag": f"Wie is het hoofdlid, is dat {ACHTERNAAM}?", "historie": "[]",
    }, headers={"X-CSRF-Token": csrf_token_for(value)})

    assert resp.status_code == 200
    # De uitklapper toont letterlijk wat de provider kreeg — dat is het bewijs.
    assert ACHTERNAAM not in resp.text or "gezin-" in resp.text
    payload = re.search(r"<pre[^>]*>(.*?)</pre>", resp.text, re.S)
    assert payload, "de payload-uitklapper ontbreekt"
    assert ACHTERNAAM not in payload.group(1)
    assert "Kerkstraat" not in payload.group(1)

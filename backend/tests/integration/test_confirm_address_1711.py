"""An e-mail address a person types himself waits for its code (CR-22 S6b, #1711; R15, F6; C6 T6).

An address is the key someone signs in with. Until this slice an address typed
in Mijn gezin or Mijn gegevens counted at once: whoever could type could sign
in as that address's owner the next minute, and a typing mistake in one's only
address locked the person out.

What holds now, each through the real doors on made-up data:

- **T6** — a typed address is stored waiting: it does not sign in, it is not
  the primary address, and "Bevestig je e-mailadres" leaves for it with a
  link and a code — as a job of the save, so only once the row is stored;
- the code AND the link of that mail make it count (Q36), and the code spends
  the token of the one code mechanism;
- **the old address stays until the new one is confirmed** (Koen, 8 October
  2026): an address typed OVER one that counts is stored beside it; the old
  one keeps signing in; at the code the new one takes its place and its
  primary mark, and a session signed in with the old address moves along;
- confirming signs nobody else in: whoever is signed in stays who he is;
- "Code opnieuw sturen" replaces the code and keeps what the row replaces;
  only one's own rows and a housemate's;
- the race: the address got an owner while it waited → the code is refused
  and nothing changes (a waiting row claims nothing);
- a waiting row that is typed over gets a new code, and the old one is dead;
- a waiting address cannot be made the primary one;
- the board's writes count at once, as before.

Broken on purpose (8 October 2026), each red for its own reason — the list
stands in the PR.
"""

from __future__ import annotations

import re
from itertools import count

import pytest

from app.domains.auth import login as auth_login
from app.domains.auth.api import (
    SESSION_COOKIE,
    LoginPurpose,
    LoginToken,
    csrf_token_for,
    make_session_value,
    read_session_value,
    sign_in_identity,
)
from app.domains.mdm.api import (
    ContactDetail,
    ContactDetailHistory,
    Person,
    add_email_address,
    email_addresses_of_members,
    new_contact_detail,
)
from app.domains.membership.api import person_block
from app.kernel.jobs import run_due_jobs
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

EMAIL = "lid-1711@example.org"
NEW = "nieuw-1711@example.org"
WAITING = "wacht op bevestiging"


@pytest.fixture(autouse=True)
def codes_that_differ(monkeypatch):
    """Every code is another one, so a test can tell the first from the second."""
    numbers = count(100001)
    monkeypatch.setattr(auth_login, "_generate_otp", lambda: f"{next(numbers):06d}")


@pytest.fixture
def sent(monkeypatch):
    """Every mail that leaves: the code mails are jobs, run by `_mails`."""
    from app.domains.mail import service

    captured: list[dict] = []

    def _capture(to_email, subject, body_html, cc=None, email_type="other"):
        captured.append({"to": to_email, "subject": subject, "body": body_html})

    monkeypatch.setattr(service, "_send", _capture)
    return captured


@pytest.fixture
def member(client, db_session):
    _household, person = create_test_family(db_session, email=EMAIL)
    person.first_name, person.last_name = "Emma", "Voorbeeld"
    db_session.commit()
    # On the domain the server sets its own cookie for, so a new session
    # REPLACES this one in the jar instead of standing beside it.
    client.cookies.set(SESSION_COOKIE, make_session_value(EMAIL), domain="testserver.local")
    return person


def _mails(db, sent: list[dict]) -> list[dict]:
    run_due_jobs(db)
    return sent


def _code(mail: dict) -> str:
    return re.search(r">(\d{6})<", mail["body"]).group(1)


def _cookie(client) -> str | None:
    """The session value as the server reads it: the jar keeps the quotes
    the server wrote around a value with a `|` in it."""
    raw = client.cookies.get(SESSION_COOKIE)
    return raw.strip('"') if raw else raw


def _csrf(client) -> dict:
    return {"X-CSRF-Token": csrf_token_for(_cookie(client))}


def _form(db, person, *, changed: dict | None = None, new=(), primary: str | None = None) -> dict:
    """What Mijn gegevens sends for this person: its rows as they are, with
    `changed` ({row id: text}) typed over and `new` addresses added."""
    db.expire_all()
    block = person_block(db.get(Person, person.id), edit=True)
    key = block.person.key
    data = {
        "h_order": key,
        f"h.{key}.first_name": block.person.first_name,
        f"h.{key}.last_name": block.person.last_name,
        f"h.{key}.mobile": block.person.mobile,
        f"e_order.{key}": [m.key for m in block.person.emails],
        f"e_primary.{key}": primary or block.person.primary_key,
    }
    for mail in block.person.emails:
        data[f"e.{mail.key}.value"] = (changed or {}).get(int(mail.key), mail.value)
    for number, address in enumerate(new):
        data[f"e_order.{key}"].append(f"n{number}")
        data[f"e.n{number}.value"] = address
    return data


def _save(client, data: dict):
    answer = client.post("/mijn/gegevens", data=data, headers=_csrf(client))
    assert answer.status_code == 200, answer.text[:300]
    return answer


def _rows(db, person) -> dict[str, tuple[bool, bool]]:
    """address → (primary, counts)."""
    db.expire_all()
    return {
        c.value: (bool(c.is_primary), c.confirmed_at is not None)
        for c in db.get(Person, person.id).contact_details
        if c.contact_type_code == "EMAIL"
    }


def _row(db, value: str) -> ContactDetail:
    return db.query(ContactDetail).filter_by(value=value).one()


def _enter(client, email: str, code: str, back: str = "/mijn/gegevens"):
    return client.post("/aanmelden/code", data={"email": email, "code": code, "terug": back})


def _session(client) -> str | None:
    return read_session_value(_cookie(client))


def _actions(db, person) -> list[str]:
    return [
        h.action
        for h in db.query(ContactDetailHistory)
        .filter_by(person_id=person.id)
        .order_by(ContactDetailHistory.id)
    ]


# ── T6: a typed address waits ────────────────────────────────────────────────


def test_a_typed_address_waits_and_its_code_is_mailed(client, db_session, member, sent):
    answer = _save(client, _form(db_session, member, new=[NEW]))
    assert _rows(db_session, member) == {EMAIL: (True, True), NEW: (False, False)}
    assert sign_in_identity(db_session, NEW)[1] is None, "a waiting address signed in"

    [mail] = _mails(db_session, sent)
    assert mail["to"] == NEW and "Bevestig je e-mailadres" in mail["subject"]
    assert "/login/verify?token=" in mail["body"] and _code(mail)

    # The row says it waits, and offers the two ways on — where the page is read.
    row = _row(db_session, NEW)
    assert WAITING in answer.text
    assert f'href="/mijn/e-mailadres/{row.id}/bevestigen"' in answer.text
    assert f'hx-post="/mijn/e-mailadres/{row.id}/code"' in answer.text
    edit = client.get("/mijn/gegevens?bewerken=1").text
    assert WAITING in edit and "data-enter-code" not in edit
    # Mijn gezin shows the same row.
    assert WAITING in client.get("/leden/gezin").text


def test_no_mail_for_a_save_that_was_refused(client, db_session, member, sent):
    """The mail is a job of the save's own transaction: a refused save — here a
    blank name — stores no row, no token and no mail."""
    data = _form(db_session, member, new=[NEW])
    data[f"h.{member.id}.first_name"] = ""
    client.post("/mijn/gegevens", data=data, headers=_csrf(client))
    assert _rows(db_session, member) == {EMAIL: (True, True)}
    assert _mails(db_session, sent) == []
    assert db_session.query(LoginToken).count() == 0


def test_the_code_makes_it_count_and_signs_nobody_else_in(client, db_session, member, sent):
    _save(client, _form(db_session, member, new=[NEW]))
    [mail] = _mails(db_session, sent)

    page = client.get(f"/mijn/e-mailadres/{_row(db_session, NEW).id}/bevestigen")
    assert page.status_code == 200 and NEW in page.text
    assert 'hx-post="/aanmelden/code"' in page.text and f'value="{NEW}"' in page.text

    answer = _enter(client, NEW, _code(mail))
    assert answer.headers.get("HX-Redirect") == "/mijn/gegevens", answer.text[:300]
    assert _rows(db_session, member) == {EMAIL: (True, True), NEW: (False, True)}
    assert sign_in_identity(db_session, NEW)[1].id == member.id
    assert _session(client) == EMAIL, "confirming an address changed who is signed in"
    assert _actions(db_session, member)[-2:] == ["email_added", "email_confirmed"]
    token = db_session.query(LoginToken).one()
    assert token.purpose is LoginPurpose.CONFIRM_ADDRESS and token.used
    # The page of a row that counts is gone, and so is its badge.
    assert client.get(f"/mijn/e-mailadres/{_row(db_session, NEW).id}/bevestigen").status_code == 404
    assert WAITING not in client.get("/mijn/gegevens").text


def test_the_link_of_the_mail_confirms_too(client, db_session, member, sent):
    """Q36: the link does what the code does. Opened where nobody is signed in
    — another device — it signs in with the address it proved."""
    _save(client, _form(db_session, member, new=[NEW]))
    [mail] = _mails(db_session, sent)
    link = re.search(r'href="[^"]*(/login/verify\?token=[^"&]+)', mail["body"]).group(1)
    client.cookies.clear()
    answer = client.get(link, follow_redirects=False)
    assert answer.status_code == 302 and answer.headers["location"] == "/mijn"
    assert _rows(db_session, member)[NEW] == (False, True)
    assert _session(client) == NEW


# ── the old address stays until the new one is confirmed ─────────────────────


def test_a_changed_address_keeps_the_old_one_until_the_code(client, db_session, member, sent):
    old = _row(db_session, EMAIL)
    _save(client, _form(db_session, member, changed={old.id: NEW}))
    assert _rows(db_session, member) == {EMAIL: (True, True), NEW: (False, False)}, (
        "the address that counts was changed before the new one was proven"
    )
    assert sign_in_identity(db_session, EMAIL)[1].id == member.id, "the old address stopped"

    [mail] = _mails(db_session, sent)
    answer = _enter(client, NEW, _code(mail))
    assert answer.headers.get("HX-Redirect") == "/mijn/gegevens"
    assert _rows(db_session, member) == {NEW: (True, True)}, "the new address did not take over"
    assert sign_in_identity(db_session, EMAIL)[1] is None
    # The session was signed in with the address that is gone: it moves along.
    assert _session(client) == NEW
    assert client.get("/mijn/gegevens").status_code == 200
    assert _actions(db_session, member)[-4:] == [
        "email_added",
        "email_promoted",
        "email_replaced",
        "email_confirmed",
    ]


def test_the_same_address_in_other_capitals_is_no_new_address(client, db_session, member, sent):
    old = _row(db_session, EMAIL)
    _save(client, _form(db_session, member, changed={old.id: EMAIL.upper()}))
    assert _rows(db_session, member) == {EMAIL.upper(): (True, True)}
    assert _mails(db_session, sent) == []


# ── "Code opnieuw sturen" ────────────────────────────────────────────────────


def test_code_again_replaces_the_code_and_keeps_what_the_row_replaces(
    client, db_session, member, sent
):
    old = _row(db_session, EMAIL)
    _save(client, _form(db_session, member, changed={old.id: NEW}))
    row = _row(db_session, NEW)
    answer = client.post(
        f"/mijn/e-mailadres/{row.id}/code",
        headers=_csrf(client) | {"HX-Current-URL": "http://testserver/leden/gezin"},
    )
    assert answer.status_code == 200
    assert (
        answer.headers["HX-Redirect"] == f"/mijn/e-mailadres/{row.id}/bevestigen?terug=/leden/gezin"
    )

    first, second = _mails(db_session, sent)
    assert second["to"] == NEW and _code(first) != _code(second)
    assert _enter(client, NEW, _code(first)).headers.get("HX-Redirect") is None, (
        "the first code still worked after a second one was sent"
    )
    assert _enter(client, NEW, _code(second)).headers.get("HX-Redirect")
    assert _rows(db_session, member) == {NEW: (True, True)}, (
        "asking the code again turned a replacement into an extra address"
    )


def test_code_again_needs_the_session_and_its_token(client, db_session, member, sent):
    _save(client, _form(db_session, member, new=[NEW]))
    row = _row(db_session, NEW)
    assert client.post(f"/mijn/e-mailadres/{row.id}/code").status_code == 403
    client.cookies.clear()
    assert client.post(f"/mijn/e-mailadres/{row.id}/code").status_code == 401
    answer = client.get(f"/mijn/e-mailadres/{row.id}/bevestigen", follow_redirects=False)
    assert answer.status_code == 302 and answer.headers["location"].startswith("/aanmelden?terug=")
    assert len(_mails(db_session, sent)) == 1, "a code was sent without a session"


def test_only_ones_own_rows_and_a_housemates(client, db_session, member, sent):
    # A stranger's waiting row: not mine.
    _other_household, stranger = create_test_family(db_session, email="ander-1711@example.org")
    theirs = new_contact_detail(
        db_session, stranger, "EMAIL", "vreemd-1711@example.org", is_primary=False, confirmed=False
    )
    db_session.add(theirs)
    # A housemate's waiting row: the household is edited as one.
    household = member.member_persons[0].member
    _same, housemate = create_test_family(db_session, email="huis-1711@example.org")
    housemate.member_persons[0].member_id = household.id
    housemate.member_persons[0].relation_type = "PARTNER"
    db_session.flush()
    ours = new_contact_detail(
        db_session,
        housemate,
        "EMAIL",
        "partner-1711@example.org",
        is_primary=False,
        confirmed=False,
    )
    db_session.add(ours)
    db_session.commit()

    assert (
        client.post(f"/mijn/e-mailadres/{theirs.id}/code", headers=_csrf(client)).status_code == 404
    )
    assert client.get(f"/mijn/e-mailadres/{theirs.id}/bevestigen").status_code == 404
    assert _mails(db_session, sent) == []
    # A row that counts has no code to send either.
    counted = _row(db_session, EMAIL)
    assert (
        client.post(f"/mijn/e-mailadres/{counted.id}/code", headers=_csrf(client)).status_code
        == 404
    )

    assert (
        client.post(f"/mijn/e-mailadres/{ours.id}/code", headers=_csrf(client)).status_code == 200
    )
    [mail] = _mails(db_session, sent)
    assert mail["to"] == "partner-1711@example.org"
    # The parent confirms the partner's address and stays who he is.
    assert _enter(client, "partner-1711@example.org", _code(mail)).headers.get("HX-Redirect")
    assert _session(client) == EMAIL


# ── refusals at the code ─────────────────────────────────────────────────────


def test_an_address_that_got_an_owner_while_it_waited_is_refused(client, db_session, member, sent):
    """The race (C5): a waiting row claims nothing, so somebody else may have
    confirmed the address meanwhile. One owner, not two — and nothing changes."""
    old = _row(db_session, EMAIL)
    _save(client, _form(db_session, member, changed={old.id: NEW}))
    [mail] = _mails(db_session, sent)
    _household, other = create_test_family(db_session, email="ander-1711@example.org")
    add_email_address(db_session, other.id, NEW, actor="bestuur@example.com")

    answer = _enter(client, NEW, _code(mail))
    assert answer.headers.get("HX-Redirect") is None
    assert "data-error" in answer.text or 'role="alert"' in answer.text, answer.text[:300]
    assert _rows(db_session, member) == {EMAIL: (True, True), NEW: (False, False)}
    assert sign_in_identity(db_session, NEW)[1].id == other.id
    assert _session(client) == EMAIL
    assert db_session.query(LoginToken).filter_by(email=NEW).one().used, (
        "the code can be tried again"
    )


def test_a_waiting_row_typed_over_gets_a_new_code_and_the_old_one_is_dead(
    client, db_session, member, sent
):
    other = "anders-1711@example.org"
    _save(client, _form(db_session, member, new=[NEW]))
    row = _row(db_session, NEW)
    _save(client, _form(db_session, member, changed={row.id: other}))
    assert _rows(db_session, member) == {EMAIL: (True, True), other: (False, False)}, (
        "a waiting row typed over became a second waiting row"
    )
    first, second = _mails(db_session, sent)
    assert (first["to"], second["to"]) == (NEW, other)

    refused = _enter(client, NEW, _code(first))
    assert refused.headers.get("HX-Redirect") is None, "the code of the old text confirmed the new"
    assert _rows(db_session, member)[other] == (False, False)
    assert _enter(client, other, _code(second)).headers.get("HX-Redirect")
    assert _rows(db_session, member)[other] == (False, True)


def test_a_waiting_address_cannot_be_made_the_primary_one(client, db_session, member, sent):
    _save(client, _form(db_session, member, new=[NEW]))
    row = _row(db_session, NEW)
    _save(client, _form(db_session, member, primary=str(row.id)))
    assert _rows(db_session, member) == {EMAIL: (True, True), NEW: (False, False)}


def test_a_new_address_marked_as_the_primary_one_becomes_it_at_its_code(
    client, db_session, member, sent
):
    """Adding an address and making it the main one is one save (#1590). The
    mark waits with the address — also when the code is asked a second time.
    Red when the wish does not travel with the code."""
    data = _form(db_session, member, new=[NEW], primary="n0")
    _save(client, data)
    assert _rows(db_session, member) == {EMAIL: (True, True), NEW: (False, False)}
    client.post(f"/mijn/e-mailadres/{_row(db_session, NEW).id}/code", headers=_csrf(client))
    _first, second = _mails(db_session, sent)
    assert _enter(client, NEW, _code(second)).headers.get("HX-Redirect")
    assert _rows(db_session, member) == {EMAIL: (False, True), NEW: (True, True)}
    assert _actions(db_session, member)[-3:] == [
        "email_demoted",
        "email_promoted",
        "email_confirmed",
    ]


def test_a_first_address_becomes_the_primary_one_at_its_code(client, db_session, member, sent):
    """Whoever has no primary address gets one when his address is confirmed —
    not before: a waiting address receives nothing."""
    old = _row(db_session, EMAIL)
    data = _form(db_session, member, new=[NEW])
    data[f"e.{old.id}.value"] = ""
    _save(client, data)
    assert _rows(db_session, member) == {NEW: (False, False)}
    [mail] = _mails(db_session, sent)
    # His session's address is gone and the new one does not sign in yet: the
    # link of the mail is his way back in.
    client.cookies.clear()
    link = re.search(r'href="[^"]*(/login/verify\?token=[^"&]+)', mail["body"]).group(1)
    assert client.get(link, follow_redirects=False).status_code == 302
    assert _rows(db_session, member) == {NEW: (True, True)}


# ── the board ────────────────────────────────────────────────────────────────


def test_what_the_board_types_counts_at_once(db_session, member, sent):
    add_email_address(db_session, member.id, NEW, actor="bestuur@example.com")
    assert _rows(db_session, member) == {EMAIL: (True, True), NEW: (False, True)}
    assert _mails(db_session, sent) == []


def test_a_waiting_address_gets_no_newsletter(client, db_session, member, sent):
    """The member audience is every address of every person of the household
    (#1174) — every address that COUNTS. Red when the audience takes a
    waiting row along: a typing mistake would mail a stranger."""
    household = member.member_persons[0].member_id
    _save(client, _form(db_session, member, new=[NEW]))
    db_session.expire_all()
    assert email_addresses_of_members(db_session, [household]) == [EMAIL]
    [mail] = _mails(db_session, sent)
    assert _enter(client, NEW, _code(mail)).headers.get("HX-Redirect")
    db_session.expire_all()
    assert email_addresses_of_members(db_session, [household]) == sorted([EMAIL, NEW])

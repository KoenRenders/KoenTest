"""Signing in with an account: who an address signs in as, the codes per purpose, the landing (CR-22 S4a, #1707).

Everyone who signs in has an account — a person in master data. Until now only
a board user or the persons of one household could get a code; a person
without a household could not, and after signing in everyone landed on Mijn
gezin, which an account does not have.

What this file holds, by the test numbers of the change request (C6):

- **T1, T3** — `sign_in_identity`: one household → the main member when he
  holds the address himself, else the holder; one person without a household
  → that person; anything that does not say who signs in → nobody; an
  unconfirmed address counts for nothing.
- **T2** — `/aanmelden`: an account's address gets a code, an unknown one gets
  nothing, and the screen says the same.
- **T4, T5** — making an account: four required fields; no person before the
  code; the code and the link of the mail both make it; an existing address
  gets the same answer and the mail "Je hebt al een account".
- **Missing in C6, asked on the issue** — the link for CREATE_ACCOUNT; the
  lockout on its code; the race: the address gets an owner between the form
  and the code → one refusal, not two owners.
- **T9** — the landing: a member and an account on `/mijn`; a page that asked
  still wins.
- **T13** — the confirmation mail links to Mijn inschrijvingen for a
  registration with a person; a guest's has no link.
- **T16** — a members-only activity refuses an account.

On made-up data, through the real routes where a route exists. The screen
"Account aanmaken" is the slice after this one (#1708); until then the request
is made through `start_account`, which that screen will call.

Broken on purpose (8 October 2026), each red for its own reason — see the PR
for the list: the confirmed filter out of the lookup; the account branch out of
`sign_in_identity`; `start_login` deaf to an account; the person made when the
form is sent instead of at the code; the re-check at the code taken out; the
tenant check taken out; the landing back on Mijn gezin; the link in a guest's
mail.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.activities.api import members_only_refusal
from app.domains.auth import login as auth_login
from app.domains.auth.api import (
    SESSION_COOKIE,
    AccountRequest,
    AccountRequestInvalid,
    LoginPurpose,
    LoginToken,
    User,
    UserRole,
    consume_code,
    landing_for,
    login_person_for_email,
    make_session_value,
    sign_in_identity,
    start_account,
)
from app.domains.mdm.api import (
    ContactDetail,
    Member,
    MemberPerson,
    Person,
    PersonHistory,
    new_contact_detail,
)
from app.kernel.jobs import run_due_jobs
from app.kernel.tenancy import TENANT_VOORBEELD_ID, current_tenant_id
from tests.conftest import register_at_the_door, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

CODE = "424242"
SAME_ANSWER = "We stuurden"  # the code step's sentence starts the same for everyone


@pytest.fixture(autouse=True)
def a_known_code(monkeypatch):
    monkeypatch.setattr(auth_login, "_generate_otp", lambda: CODE)


@pytest.fixture
def sent(monkeypatch):
    """Every mail that leaves, whichever way: sent at once (the sign-in mail)
    or queued as a job (the account mails) and run by `_mails`."""
    from app.domains.mail import service

    captured: list[dict] = []

    def _capture(to_email, subject, body_html, cc=None, email_type="other"):
        captured.append({"to": to_email, "subject": subject, "body": body_html, "type": email_type})

    monkeypatch.setattr(service, "_send", _capture)
    return captured


def _mails(db, sent: list[dict]) -> list[dict]:
    run_due_jobs(db)
    return sent


def _person(db, first_name, *, household=None, relation="HOOFDLID", email=None, confirmed=True):
    person = Person(
        date_of_birth=date(1980, 1, 1), gender_code="M", first_name=first_name, last_name="Proef"
    )
    db.add(person)
    db.flush()
    if household is not None:
        db.add(MemberPerson(member_id=household.id, person_id=person.id, relation_type=relation))
        db.flush()
    if email:
        db.add(new_contact_detail(db, person, "EMAIL", email, is_primary=True, confirmed=confirmed))
        db.flush()
    return person


def _household(db):
    household = Member()
    db.add(household)
    db.flush()
    return household


def _request(email="nieuw@example.com", **more) -> AccountRequest:
    fields = {"first_name": "Nora", "last_name": "Nieuw", "email": email, "mobile": "0470000001"}
    return AccountRequest(**(fields | more))


def _persons(db) -> int:
    db.expire_all()
    return db.query(Person).count()


# ── T1, T3: who an address signs in as ───────────────────────────────────────


def test_a_shared_household_address_signs_in_as_the_main_member(db_session):
    """R21: the household acts as one. The partner was added FIRST, so "the
    first holder" would be her."""
    household = _household(db_session)
    partner = _person(db_session, "Partner", household=household, relation="PARTNER")
    main = _person(db_session, "Hoofd", household=household, email="gezin@example.com")
    db_session.add(
        ContactDetail(person_id=partner.id, contact_type_code="EMAIL", value="gezin@example.com")
    )
    db_session.commit()
    assert sign_in_identity(db_session, "Gezin@Example.com") == ("ok", main)


def test_a_partner_with_an_address_of_his_own_signs_in_as_himself(db_session):
    """F1 as the code does it: the main member only when HE holds the address."""
    household = _household(db_session)
    _person(db_session, "Hoofd", household=household, email="hoofd@example.com")
    partner = _person(
        db_session, "Partner", household=household, relation="PARTNER", email="partner@example.com"
    )
    db_session.commit()
    assert login_person_for_email(db_session, "partner@example.com") == partner


def test_a_person_without_a_household_is_an_account(db_session):
    """Red on master: None — an account could not sign in."""
    account = _person(db_session, "Account", email="account@example.com")
    db_session.commit()
    assert sign_in_identity(db_session, "account@example.com") == ("account", account)
    assert login_person_for_email(db_session, "account@example.com") == account


def test_an_address_that_does_not_say_who_signs_in_signs_nobody_in(db_session):
    """Cases the rule of master data refuses from now on, and that may exist
    from before: made here without the factory, as old rows were."""
    first, second = _household(db_session), _household(db_session)
    for name, household in (("Een", first), ("Twee", second), ("Los", None), ("Ander", None)):
        _person(db_session, name, household=household)
    people = {p.first_name: p for p in db_session.query(Person)}

    def give(name, address):
        db_session.add(
            ContactDetail(person_id=people[name].id, contact_type_code="EMAIL", value=address)
        )

    give("Een", "tweegezinnen@example.com")
    give("Twee", "tweegezinnen@example.com")
    give("Los", "tweeaccounts@example.com")
    give("Ander", "tweeaccounts@example.com")
    give("Een", "gemengd@example.com")
    give("Los", "gemengd@example.com")
    db_session.commit()
    for address in ("tweegezinnen@example.com", "tweeaccounts@example.com", "gemengd@example.com"):
        assert sign_in_identity(db_session, address) == ("multiple", None), address
    assert sign_in_identity(db_session, "niemand@example.com") == ("none", None)


def test_an_address_that_waits_for_its_code_signs_nobody_in(db_session):
    """F6. Red without the confirmed filter: the person signs in."""
    _person(db_session, "Wacht", email="wacht@example.com", confirmed=False)
    db_session.commit()
    assert sign_in_identity(db_session, "wacht@example.com") == ("none", None)


# ── T2: asking a code ────────────────────────────────────────────────────────


def test_an_accounts_address_gets_a_code_and_an_unknown_one_gets_nothing(client, db_session, sent):
    """Red on master: nothing is sent to the account either. The two answers
    are the same text — a screen never tells whether an address is known."""
    _person(db_session, "Account", email="account@example.com")
    db_session.commit()
    known = client.post("/aanmelden", data={"email": "account@example.com"})
    unknown = client.post("/aanmelden", data={"email": "niemand@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.text.replace("account@", "x@") == unknown.text.replace("niemand@", "x@")
    assert [m["to"] for m in _mails(db_session, sent)] == ["account@example.com"]
    assert db_session.query(LoginToken).filter_by(email="niemand@example.com").count() == 0

    done = client.post("/aanmelden/code", data={"email": "account@example.com", "code": CODE})
    assert done.headers.get("HX-Redirect") == "/mijn"
    assert SESSION_COOKIE in done.cookies


# ── T4: making an account ────────────────────────────────────────────────────


def test_the_four_fields_are_required_each_with_its_own_refusal(db_session):
    empty = AccountRequest(first_name=" ", last_name="", email="geen-adres", mobile="")
    assert set(empty.problems()) == {"first_name", "last_name", "email", "mobile"}
    assert _request().problems() == {}
    with pytest.raises(AccountRequestInvalid) as refused:
        start_account(db_session, _request(mobile=" "))
    assert set(refused.value.problems) == {"mobile"}
    assert db_session.query(LoginToken).count() == 0


def test_no_person_before_the_code_and_one_confirmed_person_after_it(db_session, sent):
    """R3: the account exists only once the code is entered. Red when the
    person is made as the form is sent."""
    import app.main  # noqa: F401 - the handlers of mdm and mail

    before = _persons(db_session)
    start_account(db_session, _request())
    assert _persons(db_session) == before, "a person exists before the code was entered"
    token = db_session.query(LoginToken).filter_by(email="nieuw@example.com").one()
    assert token.purpose is LoginPurpose.CREATE_ACCOUNT and not token.used
    [mail] = _mails(db_session, sent)
    assert mail["to"] == "nieuw@example.com" and mail["subject"].startswith("Bevestig je account")
    assert CODE in mail["body"] and f"/login/verify?token={token.token}" in mail["body"]

    consumed = consume_code(db_session, "nieuw@example.com", CODE)
    assert consumed is not None and consumed.refusal is None
    assert consumed.purpose is LoginPurpose.CREATE_ACCOUNT

    account = login_person_for_email(db_session, "nieuw@example.com")
    assert account is not None and _persons(db_session) == before + 1
    assert (account.first_name, account.last_name) == ("Nora", "Nieuw")
    details = {c.contact_type_code: c for c in account.contact_details}
    assert set(details) == {"EMAIL", "MOBILE"}
    assert details["MOBILE"].value == "0470000001"
    assert all(c.confirmed_at is not None and c.is_primary for c in details.values())
    # R17: an account is not asked an address, a birth date or a gender.
    assert account.date_of_birth is None and account.gender_code is None
    assert account.address is None and not account.member_persons
    history = db_session.query(PersonHistory).filter_by(person_id=account.id).all()
    assert [h.action for h in history] == ["account_created"]


def test_the_link_of_the_mail_makes_the_account_too(client, db_session, sent):
    """Q36: the link and the code are the same token. Missing in C6."""
    start_account(db_session, _request())
    token = db_session.query(LoginToken).filter_by(email="nieuw@example.com").one().token
    answer = client.get(f"/login/verify?token={token}", follow_redirects=False)
    assert answer.status_code == 302 and answer.headers["location"] == "/mijn"
    assert SESSION_COOKIE in answer.cookies
    assert login_person_for_email(db_session, "nieuw@example.com") is not None
    again = client.get(f"/login/verify?token={token}", follow_redirects=False)
    assert again.status_code == 401, "a spent link works twice"
    assert db_session.query(Person).filter_by(first_name="Nora").count() == 1


# ── T5: an address that has an account ───────────────────────────────────────


def test_an_existing_address_gets_the_owner_a_sign_in_code_and_no_second_person(db_session, sent):
    """R4. Only the mail says there is an account; nothing is made."""
    owner = _person(db_session, "Eigenaar", email="nieuw@example.com")
    db_session.commit()
    before = _persons(db_session)
    start_account(db_session, _request(first_name="Indringer"))
    [mail] = _mails(db_session, sent)
    assert mail["subject"].startswith("Je hebt al een account")
    token = db_session.query(LoginToken).filter_by(email="nieuw@example.com", used=False).one()
    assert token.purpose is LoginPurpose.SIGN_IN and token.payload is None

    consumed = consume_code(db_session, "nieuw@example.com", CODE)
    assert consumed is not None and consumed.purpose is LoginPurpose.SIGN_IN
    assert _persons(db_session) == before
    assert login_person_for_email(db_session, "nieuw@example.com") == owner
    assert db_session.query(Person).filter_by(first_name="Indringer").count() == 0


# ── the limit, the race, the tenant ──────────────────────────────────────────


def test_five_wrong_codes_end_the_code_of_a_new_account(db_session, sent):
    """The lockout of #268 holds for every purpose. Missing in C6."""
    start_account(db_session, _request())
    for _attempt in range(auth_login.MAX_OTP_ATTEMPTS):
        assert consume_code(db_session, "nieuw@example.com", "000000") is None
    assert consume_code(db_session, "nieuw@example.com", CODE) is None
    assert login_person_for_email(db_session, "nieuw@example.com") is None


def test_an_address_taken_between_the_form_and_the_code_is_refused_at_the_code(
    client, db_session, sent
):
    """C5: one owner, not two. Red without the re-check at the code."""
    start_account(db_session, _request())
    somebody = _person(db_session, "Sneller", household=_household(db_session))
    db_session.add(
        new_contact_detail(db_session, somebody, "EMAIL", "nieuw@example.com", is_primary=True)
    )
    db_session.commit()
    before = _persons(db_session)

    answer = client.post("/aanmelden/code", data={"email": "nieuw@example.com", "code": CODE})
    assert "Dit e-mailadres is al in gebruik door iemand anders." in answer.text
    assert SESSION_COOKIE not in answer.cookies and "HX-Redirect" not in answer.headers
    assert _persons(db_session) == before
    assert (
        db_session.query(LoginToken).filter_by(email="nieuw@example.com", used=False).count() == 0
    )
    assert consume_code(db_session, "nieuw@example.com", CODE) is None, "the code works again"


def test_a_code_asked_at_one_tenant_makes_no_account_at_another(db_session, sent):
    """R10: accounts are per tenant, and the token itself has none."""
    start_account(db_session, _request())
    token = current_tenant_id.set(TENANT_VOORBEELD_ID)
    try:
        consumed = consume_code(db_session, "nieuw@example.com", CODE)
    finally:
        current_tenant_id.reset(token)
    assert consumed is not None and consumed.refusal
    people = db_session.query(Person).execution_options(include_all_tenants=True)
    assert people.filter(Person.first_name == "Nora").count() == 0


# ── T9: the landing ──────────────────────────────────────────────────────────


def test_a_member_and_an_account_land_on_the_account_page_and_a_board_user_on_the_site(db_session):
    _person(db_session, "Lid", household=_household(db_session), email="lid@example.com")
    _person(db_session, "Account", email="account@example.com")
    board = User(email="bestuur@example.com", is_active=True)
    db_session.add(board)
    db_session.flush()
    db_session.add(UserRole(user_id=board.id, role_code="ADMIN"))
    db_session.commit()
    assert landing_for(db_session, "lid@example.com") == "/mijn"
    assert landing_for(db_session, "account@example.com") == "/mijn"
    # #1740: the door decides, not the role — signed in on the site, a board user
    # without a person here lands on the site, with Admin in his menu.
    assert landing_for(db_session, "bestuur@example.com") == "/"


def test_the_page_that_asked_still_wins_over_the_landing(client, db_session, sent):
    """R15: the renewal link in a mail opens the renewal, not Mijn <tenant>."""
    _person(db_session, "Lid", household=_household(db_session), email="lid@example.com")
    db_session.commit()
    asked = "/leden/gezin/vernieuwen"
    client.post("/aanmelden", data={"email": "lid@example.com", "terug": asked})
    done = client.post(
        "/aanmelden/code", data={"email": "lid@example.com", "code": CODE, "terug": asked}
    )
    assert done.headers.get("HX-Redirect") == asked


def test_an_account_has_no_mijn_gezin_and_is_not_sent_round_in_a_loop(client, db_session):
    """Before: an account opening /leden/gezin was sent to sign in, and from
    there back to /leden/gezin. Now it goes to its own page, whose menu lists
    what applies — no Mijn gezin."""
    _person(db_session, "Account", email="account@example.com")
    _person(db_session, "Lid", household=_household(db_session), email="lid@example.com")
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value("account@example.com"))
    bounced = client.get("/leden/gezin", follow_redirects=False)
    assert bounced.status_code == 302 and bounced.headers["location"] == "/mijn"
    page = client.get("/mijn")
    assert page.status_code == 200
    assert 'href="/mijn/gegevens"' in page.text and 'href="/leden/gezin"' not in page.text

    client.cookies.set(SESSION_COOKIE, make_session_value("lid@example.com"))
    assert 'href="/leden/gezin"' in client.get("/mijn").text, "a member lost Mijn gezin"
    assert client.get("/leden/gezin", follow_redirects=False).status_code == 200


# ── T13: the confirmation mail ───────────────────────────────────────────────


def test_the_confirmation_mail_links_to_mijn_inschrijvingen_only_with_a_person(
    client, db_session, sent
):
    """R6. A guest has no account, so nothing to look up: no link."""
    from app.domains.activities.api import Registration
    from app.kernel.contracts.activities import RegistrationConfirmed
    from app.kernel.events import publish

    _activity, component, product = seed_activity_with_product(db_session, is_free=True)
    answer = register_at_the_door(
        client,
        component.activity_id,
        json={
            "contact_name": "Gast Proef",
            "phone": "0470000002",
            "contact_email": "gast@example.com",
            "component_id": component.id,
            "items": [{"product_id": product.id, "quantity": 1}],
        },
    )
    assert answer.status_code in (200, 201), answer.text
    [guest_mail] = _mails(db_session, sent)
    assert "/mijn/inschrijvingen" not in guest_mail["body"]

    registration = db_session.query(Registration).one()
    registration.person_id = _person(db_session, "Account", email="account@example.com").id
    db_session.flush()
    publish(
        RegistrationConfirmed(
            registration_id=registration.id, to_email="account@example.com", name="Account Proef"
        ),
        db_session,
    )
    db_session.commit()
    signed_in_mail = _mails(db_session, sent)[-1]
    assert signed_in_mail["to"] == "account@example.com"
    assert "/mijn/inschrijvingen" in signed_in_mail["body"]


# ── T16: what stays as it is ─────────────────────────────────────────────────


def test_a_members_only_activity_refuses_an_account(db_session):
    """R20: an account is a person, not a member with a valid membership."""
    activity, _component, _product = seed_activity_with_product(db_session, is_free=True)
    activity.members_only = True
    account = _person(db_session, "Account", email="account@example.com")
    db_session.commit()
    assert members_only_refusal(db_session, activity, account.id) == (
        "Deze activiteit is enkel voor leden met een geldig lidmaatschap."
    )

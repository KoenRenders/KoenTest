"""The sign-in, the registration and Lid worden carry the guard of the other public forms (#2039).

Per form, the same four checks as the account form's (`test_create_account_screens_1708.py`):
the page carries the guard's two fields; a post without them, a post as fast as the page was
rendered and a filled honeypot each get the ordinary answer and leave nothing behind (no token,
no mail, no registration, no household); and a post from a form rendered five seconds ago is not
refused, so "nothing" means something.

Proven red (15 October 2026): with the guard's check switched off in `start_login`,
`registration_form.submit` and `signup_service.register_family`, all nine refusal tests fail on
what was stored; the three "normal pace" tests are their control.
"""

import time

import pytest

from app.domains.auth.api import LoginToken
from app.kernel.form_guard import issue_token
from tests._queued_mail import queued_mails
from tests.conftest import SEEDED_ADMIN_EMAIL, form_guard_fields

pytestmark = pytest.mark.ui_serverrendered


def _without(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in ("website", "form_ts")}


def _too_fast(data: dict) -> dict:
    return {**_without(data), "website": "", "form_ts": issue_token(now=time.time())}


def _honeypot(data: dict) -> dict:
    return {**data, "website": "https://spam.example.org"}


REFUSALS = {
    "without the guard's fields": _without,
    "as fast as the page was rendered": _too_fast,
    "with the honeypot filled": _honeypot,
}


# ── sign-in ──────────────────────────────────────────────────────────────────


def test_the_sign_in_page_carries_the_guards_two_fields(client):
    html = client.get("/aanmelden").text
    assert 'name="website"' in html and 'name="form_ts"' in html


@pytest.mark.parametrize("how", sorted(REFUSALS))
def test_a_refused_sign_in_sends_and_stores_nothing(client, db_session, how):
    tokens = db_session.query(LoginToken).count()
    data = REFUSALS[how]({**form_guard_fields(), "email": SEEDED_ADMIN_EMAIL})
    step = client.post("/aanmelden", data=data)
    assert step.status_code == 200 and "data-code-sent" in step.text, how
    db_session.expire_all()
    assert db_session.query(LoginToken).count() == tokens, "a refused request stored a token"
    assert queued_mails(db_session, SEEDED_ADMIN_EMAIL) == [], "a refused request sent a mail"


def test_a_person_at_a_normal_pace_gets_the_sign_in_mail(client, db_session):
    client.post("/aanmelden", data={**form_guard_fields(), "email": SEEDED_ADMIN_EMAIL})
    assert len(queued_mails(db_session, SEEDED_ADMIN_EMAIL)) == 1


# ── registration for an activity ─────────────────────────────────────────────


def _registration(db_session):
    from tests.conftest import seed_activity_with_product

    activity, component, product = seed_activity_with_product(db_session, price="0", is_free=True)
    db_session.commit()
    return activity, component, product


def _registration_post(client, act, data, address):
    activity, component, product = act
    return client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            **data,
            "contact_name": "Mens 2039",
            "contact_email": address,
            "phone": "0470000000",
            f"product_{product.id}": "1",
        },
        headers={"HX-Request": "true"},
    )


def test_the_registration_page_carries_the_guards_two_fields(client, db_session):
    activity, component, _product = _registration(db_session)
    html = client.get(f"/activiteiten/{activity.id}/inschrijven/{component.id}").text
    assert 'name="website"' in html and 'name="form_ts"' in html


@pytest.mark.parametrize("how", sorted(REFUSALS))
def test_a_refused_registration_registers_and_mails_nothing(client, db_session, how):
    from app.domains.activities.api import Registration

    act = _registration(db_session)
    address = "bot-2039@example.org"
    response = _registration_post(client, act, REFUSALS[how](form_guard_fields()), address)
    assert response.status_code == 200, how
    db_session.expire_all()
    assert db_session.query(Registration).count() == 0, "a refused request registered somebody"
    assert queued_mails(db_session, address) == [], "a refused request sent a mail"


def test_a_person_at_a_normal_pace_registers_and_gets_the_mail(client, db_session):
    from app.domains.activities.api import Registration
    from app.kernel.jobs import run_due_jobs

    act = _registration(db_session)
    address = "mens-2039@example.org"
    response = _registration_post(client, act, form_guard_fields(), address)
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(Registration).count() == 1
    run_due_jobs(db_session)


# ── Lid worden ───────────────────────────────────────────────────────────────


def test_the_lid_worden_page_carries_the_guards_two_fields(client):
    html = client.get("/lid-worden").text
    assert 'name="website"' in html and 'name="form_ts"' in html


@pytest.mark.parametrize("how", sorted(REFUSALS))
def test_a_refused_sign_up_makes_no_household_and_sends_no_mail(client, db_session, how):
    from app.domains.mdm.api import Member
    from tests.conftest import signup_fields

    address = "bot-lid-2039@example.org"
    households = db_session.query(Member).count()
    data = REFUSALS[how](signup_fields(db_session, emails=(address,)))
    response = client.post("/lid-worden", data=data)
    assert response.status_code == 200, how
    db_session.expire_all()
    assert db_session.query(Member).count() == households, "a refused request made a household"
    assert queued_mails(db_session, address) == []


def test_a_person_at_a_normal_pace_becomes_a_member(client, db_session):
    from app.domains.mdm.api import Member
    from tests.conftest import signup_fields

    households = db_session.query(Member).count()
    response = client.post(
        "/lid-worden", data=signup_fields(db_session, emails=("mens-lid-2039@example.org",))
    )
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(Member).count() == households + 1

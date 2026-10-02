"""A members-only activity takes registrations from members only (#1459).

Koen, 2 October 2026: `members_only` was shown — the "Enkel voor leden"
checkbox, the "enkel leden" badge — and enforced nowhere. Signed out, with an
unknown address, anyone could register for a members-only activity and pay.

Measured here:
- the service refuses a non-member and takes a member, so no way in skips it;
- signed out, the registration page sends you to sign in and back
  (`/aanmelden?terug=…`), and the code brings you back to it;
- signed in but no member: the reason, and no form;
- a POST straight to the submit route without a member session is refused —
  the screen is not the only lock;
- an activity without the flag stays open to everyone, and the board's way in
  is not held to the rule;
- Koen's choice B: a member is somebody with a valid membership TODAY — a
  household that did not renew is refused, like the member price says.

Proven red against master `f4637e40`: there the non-member is registered and
the signed-out page is the form itself.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from tests.conftest import create_test_family, form_guard_fields, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

MEMBER = "lid-1459@example.com"
STRANGER = "vreemde-1459@example.com"


@pytest.fixture
def sint(db_session):
    activity, component, product = seed_activity_with_product(db_session, price="5.00")
    activity.members_only = True
    db_session.commit()
    return activity, component, product


def _paid(db, person) -> None:
    """A membership valid today for the person's household."""
    from datetime import date

    from app.domains.membership.api import Membership

    today = date.today()
    db.add(
        Membership(
            member_id=person.member_persons[0].member_id,
            year=today.year,
            is_active=True,
            valid_from=date(today.year, 1, 1),
            valid_to=date(today.year, 12, 31),
        )
    )
    db.commit()


@pytest.fixture
def member(db_session):
    """In a household, with a membership valid today."""
    family = create_test_family(db_session, email=MEMBER)
    from app.domains.auth.api import login_person_for_email

    _paid(db_session, login_person_for_email(db_session, MEMBER))
    return family


UNPAID = "niet-betaald-1459@example.com"


@pytest.fixture
def unpaid(db_session):
    """In a household, without a valid membership: the case choice B decides."""
    return create_test_family(db_session, email=UNPAID)


@pytest.fixture
def stranger(db_session):
    """A person with an address but in no household — a known non-member."""
    from app.domains.mdm.api import ContactDetail
    from tests.conftest import create_test_person

    person = create_test_person(db_session)
    db_session.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=STRANGER))
    db_session.commit()
    return person


def _data(component, product):
    from app.schemas.activity import RegistrationCreate, RegistrationItemCreate

    return RegistrationCreate(
        contact_name="An Janssens",
        contact_email="an@example.com",
        phone="0470000000",
        component_id=component.id,
        payment_method="transfer",
        items=[RegistrationItemCreate(product_id=product.id, quantity=1)],
    )


def _person_id(db, email: str) -> int:
    from app.domains.auth.api import login_person_for_email

    return login_person_for_email(db, email).id


def test_the_service_refuses_a_non_member_and_takes_a_member(db_session, sint, member, stranger):
    from app.domains.activities.models import RegistrationRefused
    from app.domains.activities.service import register

    activity, component, product = sint
    for person_id in (None, stranger.id):
        # Refused before anything is added, so there is nothing to roll back.
        with pytest.raises(RegistrationRefused, match="enkel voor leden"):
            register(
                db_session, activity, _data(component, product), person_id=person_id, actor="x"
            )

    registration = register(
        db_session,
        activity,
        _data(component, product),
        person_id=_person_id(db_session, MEMBER),
        actor=MEMBER,
    )
    assert registration.id is not None


def test_a_household_that_did_not_renew_is_refused(db_session, client, sint, unpaid):
    """Choice B: in a household is not enough; the membership must be valid today."""
    from app.domains.activities.models import RegistrationRefused
    from app.domains.activities.service import register

    activity, component, product = sint
    with pytest.raises(RegistrationRefused, match="geldig lidmaatschap"):
        register(
            db_session,
            activity,
            _data(component, product),
            person_id=_person_id(db_session, UNPAID),
            actor=UNPAID,
        )
    client.cookies.set(SESSION_COOKIE, make_session_value(UNPAID))
    text = client.get(f"/activiteiten/{activity.id}/inschrijven/{component.id}").text
    assert "enkel voor leden met een geldig lidmaatschap" in text
    assert 'href="/leden/gezin"' in text, "the way to renew"


def test_the_board_is_not_held_to_it(db_session, sint):
    """The board registers somebody else on purpose (CR-14 §B4.1), as with a draft."""
    from app.domains.activities.service import register

    activity, component, product = sint
    registration = register(
        db_session,
        activity,
        _data(component, product),
        person_id=None,
        actor="bestuur@example.com",
        backoffice_products=True,
    )
    assert registration.id is not None


@pytest.fixture
def mail_link(monkeypatch):
    from app.domains.auth import login as auth_login

    monkeypatch.setattr(auth_login, "send_magic_link", lambda **kwargs: None)
    monkeypatch.setattr(auth_login, "_generate_otp", lambda: "424242")


def test_signed_out_the_page_asks_to_sign_in_and_comes_back(client, sint, member, mail_link):
    activity, component, _product = sint
    page = f"/activiteiten/{activity.id}/inschrijven/{component.id}"

    answer = client.get(page, follow_redirects=False)

    assert answer.status_code == 302, answer.status_code
    location = urlparse(answer.headers["location"])
    assert location.path == "/aanmelden"
    assert parse_qs(location.query)["terug"] == [page]

    client.get("/aanmelden", params={"terug": page})
    client.post("/aanmelden", data={"email": MEMBER, "terug": page})
    done = client.post("/aanmelden/code", data={"email": MEMBER, "code": "424242", "terug": page})
    assert done.headers.get("HX-Redirect") == page, "back on the registration page"
    form = client.get(page)
    assert form.status_code == 200 and "<form" in form.text and "enkel voor leden" not in form.text


def test_signed_in_but_no_member_gets_the_reason_and_no_form(client, sint, stranger):
    """Signed in, so not sent to sign in again — that would be a loop; the
    reason instead."""
    activity, component, _product = sint
    client.cookies.set(SESSION_COOKIE, make_session_value(STRANGER))

    answer = client.get(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}", follow_redirects=False
    )
    assert answer.status_code == 200, "no redirect back to sign-in"
    text = answer.text

    assert "Deze activiteit is enkel voor leden met een geldig lidmaatschap." in text
    assert 'hx-post="/activiteiten/' not in text, "no form to pay through"
    assert 'href="/leden/gezin"' in text


def _post(client, activity, component, product):
    return client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": "An Janssens",
            "contact_email": "an@example.com",
            "phone": "0470000000",
            "payment_method": "transfer",
            f"product_{product.id}": "1",
            **form_guard_fields(),
        },
    )


def test_a_post_without_a_member_session_is_refused(client, db_session, sint, stranger):
    from app.domains.activities.api import Registration

    activity, component, product = sint
    before = db_session.query(Registration).filter_by(activity_id=activity.id).count()

    signed_out = _post(client, activity, component, product)
    client.cookies.set(SESSION_COOKIE, make_session_value(STRANGER))
    no_member = _post(client, activity, component, product)

    assert "enkel voor leden" in signed_out.text and "enkel voor leden" in no_member.text
    db_session.expire_all()
    after = db_session.query(Registration).filter_by(activity_id=activity.id).count()
    assert after == before, "nothing was registered, so nothing to pay"


def test_without_the_flag_it_stays_open_to_everyone(client, db_session, sint):
    from app.domains.activities.api import Registration

    activity, component, product = sint
    activity.members_only = False
    db_session.commit()

    page = client.get(f"/activiteiten/{activity.id}/inschrijven/{component.id}")
    assert page.status_code == 200 and "<form" in page.text
    _post(client, activity, component, product)
    db_session.expire_all()
    assert db_session.query(Registration).filter_by(activity_id=activity.id).count() == 1

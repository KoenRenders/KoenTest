"""The return of a MEMBERSHIP payment reads the ledger (#1590; end state §2.6).

After a sign-up or a renewal paid online the provider sends the payer's browser
to `/betaling/succes?member=<household id>`. Until #1590 the page could not read
that address — the booking hangs on the membership, the address names the
household — and said "Je betaling wordt verwerkt" for ever: never confirmed,
never asking again. It now reads the household's newest membership with a
booking, with the same three states as a registration's return
(`activities/tests/test_payment_return_page.py`): not confirmed while the booking
is open (and the block asks again), received once the provider confirmed it, and
no claim when there is nothing to read.

Proven red: `household_payment_state` made to return None → the pending test and
the confirmed test both find "Je betaling wordt verwerkt"; made to look at the
OLDEST membership → the renewal test reads the paid year and says "ontvangen".
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domains.mdm.api import ContactDetail, MemberPerson
from app.domains.membership.api import Membership
from tests.conftest import signup_fields

pytestmark = pytest.mark.ui_serverrendered

MAIL = "online.gezin@example.com"


@pytest.fixture(autouse=True)
def _limits():
    from app.limiter import registration_limiter

    registration_limiter._calls.clear()
    yield
    registration_limiter._calls.clear()


def _sign_up_online(client, db_session) -> int:
    """A household through Word lid, paying online; its id."""
    response = client.post(
        "/lid-worden", data=signup_fields(db_session, emails=(MAIL,), payment_method="online")
    )
    assert response.headers.get("HX-Redirect", "").startswith("https://mollie.test/checkout/")
    person_id = (
        db_session.query(ContactDetail.person_id).filter(ContactDetail.value == MAIL).scalar()
    )
    return (
        db_session.query(MemberPerson.member_id)
        .filter(MemberPerson.person_id == person_id)
        .scalar()
    )


def _status_tag(html: str) -> str:
    return html.split('id="betaling-status"')[1].split(">")[0]


def test_an_unpaid_sign_up_does_not_say_received_and_asks_again(client, db_session, mock_mollie):
    member_id = _sign_up_online(client, db_session)

    html = client.get(f"/betaling/succes?member={member_id}").text

    assert "Betaling ontvangen" not in html and "Je betaling is ontvangen" not in html
    assert "Je betaling wordt verwerkt" not in html, "the page still cannot read this address"
    assert "Betaling nog niet bevestigd" in html
    assert 'data-payment-state="pending"' in _status_tag(html)
    assert f'hx-get="/betaling/succes?member={member_id}"' in _status_tag(html)
    assert 'hx-trigger="every 4s"' in _status_tag(html)


def test_a_confirmed_sign_up_says_received_in_the_memberships_words(
    client, db_session, mock_mollie
):
    member_id = _sign_up_online(client, db_session)
    # The provider's word: the webhook, which re-fetches the status (paid).
    webhook = client.post("/api/v1/payment-gateway/webhooks/mollie", data={"id": "tr_test_123"})
    assert webhook.status_code == 200, webhook.text

    html = client.get(f"/betaling/succes?member={member_id}").text

    assert "Je betaling is ontvangen" in html
    assert 'data-payment-state="confirmed"' in _status_tag(html)
    assert "hx-trigger" not in _status_tag(html)
    assert "Je lidmaatschap is actief." in html
    assert "Je inschrijving is bevestigd" not in html, "a membership is no registration"


def test_the_newest_membership_decides_not_a_year_that_was_paid_before(
    client, db_session, mock_mollie
):
    """A renewal: the household has a paid year and a new, open one. The return is
    about the payment that was just started."""
    from app.domains.membership.api import household_payment_state
    from app.domains.payment.api import create_payment_record

    member_id = _sign_up_online(client, db_session)
    client.post("/api/v1/payment-gateway/webhooks/mollie", data={"id": "tr_test_123"})
    assert household_payment_state(db_session, member_id) == "settled"

    year = date.today().year + 5
    renewal = Membership(
        member_id=member_id,
        year=year,
        valid_from=date(year, 1, 1),
        valid_to=date(year, 12, 31),
        is_active=False,
    )
    db_session.add(renewal)
    db_session.flush()
    create_payment_record(
        db=db_session,
        payable_type="membership",
        payable_id=renewal.id,
        amount=20,
        method="transfer",
        description="Renewal",
        audit_source="test",
    )
    db_session.commit()

    assert household_payment_state(db_session, member_id) == "open"
    html = client.get(f"/betaling/succes?member={member_id}").text
    assert 'data-payment-state="pending"' in _status_tag(html)
    assert "Je betaling is ontvangen" not in html


@pytest.mark.parametrize("query", ["?member=999999", "?member=abc", "?member="])
def test_a_household_the_page_cannot_read_claims_nothing(client, query):
    html = client.get(f"/betaling/succes{query}").text
    assert "Betaling ontvangen" not in html and "Je betaling is ontvangen" not in html
    assert 'data-payment-state="unknown"' in _status_tag(html)
    assert "hx-trigger" not in _status_tag(html)

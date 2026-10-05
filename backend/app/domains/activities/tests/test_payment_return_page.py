"""The page a payer lands on after the payment page never reports a received
payment before the provider confirmed it (#1589, CR-11 pilot B; end state §2.6).

`/betaling/succes?registration=<id>` is where the provider sends the payer's
BROWSER. Arriving there says the payer came back — until #1589 the page said
"Betaling ontvangen!" to anyone who opened that address, paid or not. It now
reads the ledger: confirmed when every booking of the registration is settled,
"nog niet bevestigd" while one is open (and the status block asks again), and
no claim at all when the address names nothing it can read.

Proven red: `_payment_confirmed` made to return True → the first assertion of
`test_an_unpaid_return_does_not_say_received` fails ("Betaling ontvangen" on
the page of a payment nobody made).
"""

from __future__ import annotations

import pytest

from app.domains.activities.api import Registration
from tests.conftest import seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture(autouse=True)
def _limits():
    from app.limiter import registration_limiter

    registration_limiter._calls.clear()
    yield
    registration_limiter._calls.clear()


def _register_online(client, db_session) -> int:
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00", is_free=False
    )
    response = client.post(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}",
        data={
            "contact_name": "Betaler Bea",
            "contact_email": "betaler@example.com",
            "phone": "0470000000",
            f"product_{product.id}": "1",
            "payment_method": "online",
        },
    )
    assert response.headers.get("HX-Redirect", "").startswith("https://mollie.test/checkout/")
    return db_session.query(Registration).filter_by(activity_id=activity.id).one().id


def test_an_unpaid_return_does_not_say_received(client, db_session, mock_mollie):
    registration_id = _register_online(client, db_session)

    html = client.get(f"/betaling/succes?registration={registration_id}").text

    assert "Betaling ontvangen" not in html and "Je betaling is ontvangen" not in html
    assert "Betaling nog niet bevestigd" in html
    assert 'data-payment-state="pending"' in html
    # The block asks again by itself, at this same address.
    assert f'hx-get="/betaling/succes?registration={registration_id}"' in html
    assert 'hx-trigger="every 4s"' in html


def test_a_confirmed_return_says_received_and_stops_asking(client, db_session, mock_mollie):
    registration_id = _register_online(client, db_session)
    # The provider's word: the webhook, which re-fetches the status (paid).
    webhook = client.post("/api/v1/payment-gateway/webhooks/mollie", data={"id": "tr_test_123"})
    assert webhook.status_code == 200, webhook.text

    html = client.get(f"/betaling/succes?registration={registration_id}").text

    assert "Je betaling is ontvangen" in html
    assert 'data-payment-state="confirmed"' in html
    assert "nog niet bevestigd" not in html
    assert "hx-trigger" not in html.split('id="betaling-status"')[1].split(">")[0]


@pytest.mark.parametrize("query", ["", "?member=1", "?registration=abc", "?registration=999999"])
def test_a_return_the_page_cannot_read_claims_nothing(client, query):
    html = client.get(f"/betaling/succes{query}").text
    assert "Betaling ontvangen" not in html and "Je betaling is ontvangen" not in html
    assert 'data-payment-state="unknown"' in html and "Je betaling wordt verwerkt" in html
    assert "hx-trigger" not in html.split('id="betaling-status"')[1].split(">")[0]

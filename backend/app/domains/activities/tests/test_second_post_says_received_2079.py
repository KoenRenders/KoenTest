"""A second post of the same shown form says it was already received (#2079).

#1987 answers a second post of one shown form with the first registration. Koen,
16 October 2026, to "Wat ziet wie hetzelfde formulier een tweede keer verstuurt,
maar met een andere naam of een ander e-mailadres?": "b, zodat duidelijk is dat de
tweede inschrijving niet doorging" — the thank-you page of that answer carries one
sentence and a link to the form. The first, ordinary post shows no sentence.

With an open online payment (Koen, 16 October 2026: (b)) the same page links to it
("Betaling afronden") and does not go there on its own.

Broken on purpose (16 October 2026, each put back):
- `and not outcome.repeated` taken off the redirect in `ui.py` → the online test is red
  on the redirect;
- `repeated=True` taken out of the transfer answer in `answered_again` → the
  second-post test is red on the sentence;
- `reeds_ontvangen` set to True for every thank-you in `ui.py` → the first-post
  test is red.
"""

from __future__ import annotations

import time

import pytest

from app.domains.activities.api import Registration
from app.kernel import form_guard
from tests.conftest import seed_activity_with_product

SENTENCE = "Deze inschrijving was al ontvangen. Wil je iemand anders inschrijven"


@pytest.fixture(autouse=True)
def _limits():
    from app.limiter import registration_limiter

    registration_limiter._calls.clear()
    yield
    registration_limiter._calls.clear()


def _form(act, token: str, name: str) -> dict:
    return {
        "contact_name": name,
        "contact_email": "deelnemer-2079@example.org",
        "phone": "0470000000",
        f"product_{act[2].id}": "1",
        "payment_method": "transfer",
        form_guard.HONEYPOT_FIELD: "",
        form_guard.TOKEN_FIELD: token,
    }


def _post(client, act, data):
    client.cookies.clear()
    return client.post(
        f"/activiteiten/{act[0].id}/inschrijven/{act[1].id}",
        data=data,
        headers={"HX-Request": "true"},
    )


def test_a_second_post_with_another_name_says_so_and_registers_nobody(client, db_session):
    act = seed_activity_with_product(db_session, price="10.00")
    token = form_guard.issue_token(now=time.time() - 5)
    first = _post(client, act, _form(act, token, "Eerste Persoon"))
    second = _post(client, act, _form(act, token, "Tweede Persoon"))

    assert first.status_code == second.status_code == 200
    assert SENTENCE not in first.text
    assert SENTENCE in second.text
    assert f'href="/activiteiten/{act[0].id}/inschrijven/{act[1].id}"' in second.text
    assert "Eerste Persoon" in second.text
    assert "Tweede Persoon" not in second.text
    saved = db_session.query(Registration).filter(Registration.activity_id == act[0].id).all()
    assert [r.contact_name for r in saved] == ["Eerste Persoon"]


def test_a_second_online_post_says_so_and_links_to_the_open_payment(
    client, db_session, mock_mollie
):
    act = seed_activity_with_product(db_session, price="10.00")
    token = form_guard.issue_token(now=time.time() - 5)
    first = _post(client, act, {**_form(act, token, "Eerste Persoon"), "payment_method": "online"})
    second = _post(client, act, {**_form(act, token, "Tweede Persoon"), "payment_method": "online"})

    assert first.headers["HX-Redirect"] == "https://mollie.test/checkout/tr_test_123"
    assert "HX-Redirect" not in second.headers, "the repeat went to the payment on its own"
    assert SENTENCE in second.text
    assert 'href="https://mollie.test/checkout/tr_test_123"' in second.text
    assert "Betaling afronden" in second.text
    saved = db_session.query(Registration).filter(Registration.activity_id == act[0].id).all()
    assert [r.contact_name for r in saved] == ["Eerste Persoon"]


def test_a_first_post_shows_no_such_sentence(client, db_session):
    act = seed_activity_with_product(db_session, price="10.00")
    token = form_guard.issue_token(now=time.time() - 5)
    first = _post(client, act, _form(act, token, "Alleen Persoon"))
    assert first.status_code == 200
    assert "Je inschrijving is ontvangen" in first.text
    assert "al ontvangen" not in first.text

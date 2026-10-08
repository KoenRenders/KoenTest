"""Own words for a first membership (#1730; Koen, 8 October 2026).

The Lidmaatschap card told a first membership from no renewal: every open
membership payment was a "vernieuwing", also for a household that never was a
paid member. Now:

- **a household without a paid membership** reads "Aanmelding geregistreerd —
  betaal via overschrijving:" on its transfer block, and "Lidmaatschap betalen"
  on the way to a (new) payment — also when its first payment failed;
- **a household that has had a paid membership** keeps "Vernieuwing
  geregistreerd …" and "Lidmaatschap vernieuwen";
- the distinction is the service's (`membership.is_first_membership`), computed
  once; the landing page shows the same card with the same words.

Red (each restored after): `is_first_membership` returning False always → the
first household reads "Vernieuwing" and "vernieuwen"; returning True always →
the renewing household reads "Aanmelding" and "betalen"; the `first=` taken off
the call in `membership_card` → the transfer block says "Vernieuwing" for a
first membership while the button says "betalen".

**Since #1737** (Koen, 8 October 2026: "ja op 1" to one wording for new and
existing members) the sentences are ONE for everyone, and `is_first_membership`
decides the card's button only:

| Place | For everyone |
|---|---|
| the card, while a payment is open | "Je betaling loopt nog." |
| the transfer block | "Lidmaatschap geregistreerd — betaal via overschrijving:" |
| the title of the page behind the button | "Lidmaatschap betalen" |
| the button of that page, paying online | "Betalen" |

The tests of #1730 above are turned round where they held the two sentences
apart; the ones at the end of this file hold the table, each for a household
that never paid and for one that did.

Red for #1737 (each restored after): the card's old line put back → both
households read "vernieuwing"; the transfer block's old sentence put back →
"Vernieuwing geregistreerd" for both; the online inset repeating the card's
line → the sentence stands twice; the page's old title or old button put back
→ "Lidmaatschap vernieuwen" above a first payment, "Vernieuwen en betalen" on
its button; `pay_label` returning one word for both → the two buttons read the
same.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.membership.api import Membership, is_first_membership
from app.domains.payment.api import PaymentRecord
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

HOUSEHOLD = "/leden/gezin"
# #1737 (Koen, 8 October 2026): one sentence for a first membership and a
# renewal alike; only the card's button still tells them apart. The two
# sentences this file was written for are gone, and must stay gone.
REGISTERED = "Lidmaatschap geregistreerd — betaal via overschrijving:"
GONE = ("Aanmelding geregistreerd", "Vernieuwing geregistreerd")
PAY = "Lidmaatschap betalen"
RENEW = "Lidmaatschap vernieuwen"


def _card(html: str) -> str:
    start = html.index("data-membership-status")
    return html[start : html.index("</section>", start)]


def _sign_in(client, email: str) -> None:
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def _membership(db, member, *, year: int, paid: bool, method="transfer", status="pending"):
    """A membership of `year`: paid (active, no open booking), or waiting for
    its payment with a booking in `status`."""
    membership = Membership(
        member_id=member.id,
        year=year,
        is_active=paid,
        valid_from=date(year, 1, 1),
        valid_to=date(year, 12, 31),
    )
    db.add(membership)
    db.flush()
    if not paid:
        db.add(
            PaymentRecord(
                payable_type="membership",
                payable_id=membership.id,
                amount=Decimal("35.00"),
                method=method,
                status=status,
                structured_communication="+++173/0000/00173+++",
            )
        )
    db.commit()
    return membership


def test_the_service_tells_a_first_membership_from_a_renewal(db_session):
    never, _p = create_test_family(db_session, email="nooit-1730@example.org")
    assert is_first_membership(db_session, never)
    _membership(db_session, never, year=date.today().year, paid=False)
    assert is_first_membership(db_session, never), "a membership that waits is not a paid one"
    before, _q = create_test_family(db_session, email="vroeger-1730@example.org")
    _membership(db_session, before, year=date.today().year - 2, paid=True)
    assert not is_first_membership(db_session, before), "an expired paid membership counts"


def test_a_first_membership_by_transfer_reads_as_a_renewal_does(client, db_session):
    member, _person = create_test_family(db_session, email="eerste-1730@example.org")
    _membership(db_session, member, year=date.today().year, paid=False)
    _sign_in(client, "eerste-1730@example.org")
    card = _card(client.get(HOUSEHOLD).text)
    assert REGISTERED in card and not any(old in card for old in GONE)
    assert "+++173/0000/00173+++" in card and "35,00" in card
    # The landing page shows the same card, with the same words.
    landing = _card(client.get("/mijn").text)
    assert REGISTERED in landing and not any(old in landing for old in GONE)


def test_a_first_membership_with_an_open_online_payment_has_no_renewal_button(client, db_session):
    member, _person = create_test_family(db_session, email="online-1730@example.org")
    _membership(db_session, member, year=date.today().year, paid=False, method="online")
    _sign_in(client, "online-1730@example.org")
    card = _card(client.get(HOUSEHOLD).text)
    assert "data-renewal-online" in card
    assert RENEW not in card and PAY not in card, "a second payment is offered while one runs"


def test_a_first_payment_that_failed_offers_lidmaatschap_betalen(client, db_session):
    member, _person = create_test_family(db_session, email="mislukt-1730@example.org")
    _membership(
        db_session, member, year=date.today().year, paid=False, method="online", status="failed"
    )
    _sign_in(client, "mislukt-1730@example.org")
    card = _card(client.get(HOUSEHOLD).text)
    assert f">{PAY}</a>" in card.replace("\n", "") or PAY in card
    assert RENEW not in card
    assert 'href="/leden/gezin/vernieuwen"' in card


def test_a_household_that_was_a_paid_member_keeps_vernieuwen(client, db_session):
    member, _person = create_test_family(db_session, email="lid-1730@example.org")
    _membership(db_session, member, year=date.today().year - 1, paid=True)
    _sign_in(client, "lid-1730@example.org")
    card = _card(client.get(HOUSEHOLD).text)
    assert RENEW in card and PAY not in card

    _membership(db_session, member, year=date.today().year, paid=False)
    running = _card(client.get(HOUSEHOLD).text)
    assert REGISTERED in running and not any(old in running for old in GONE)


# ── #1737: one wording for a first membership and a renewal ─────────────────

RUNNING = "Je betaling loopt nog."
PAGE = "/leden/gezin/vernieuwen"


def _household(db, kind: str, email: str):
    """A household that never had a paid membership (`never`) or one whose
    paid membership of last year ran out (`before`)."""
    member, _person = create_test_family(db, email=email)
    if kind == "before":
        _membership(db, member, year=date.today().year - 1, paid=True)
    return member


@pytest.mark.parametrize("kind", ["never", "before"])
def test_an_open_transfer_reads_the_same_for_everyone(client, db_session, kind):
    email = f"overschrijving-{kind}-1737@example.com"
    member = _household(db_session, kind, email)
    _membership(db_session, member, year=date.today().year, paid=False)
    _sign_in(client, email)
    card = _card(client.get(HOUSEHOLD).text)
    assert RUNNING in card and REGISTERED in card
    for old in (*GONE, "Je vernieuwing loopt nog"):
        assert old not in card, old


@pytest.mark.parametrize("kind", ["never", "before"])
def test_an_open_online_payment_reads_the_same_for_everyone(client, db_session, kind):
    email = f"online-{kind}-1737@example.com"
    member = _household(db_session, kind, email)
    _membership(db_session, member, year=date.today().year, paid=False, method="online")
    _sign_in(client, email)
    card = _card(client.get(HOUSEHOLD).text)
    assert RUNNING in card and "De betaling is nog niet afgerond." in card
    assert "vernieuwing loopt" not in card
    # The line and the inset do not say the same sentence twice.
    assert card.count("Je betaling loopt nog") == 1


@pytest.mark.parametrize(("kind", "button"), [("never", PAY), ("before", RENEW)])
def test_the_cards_button_is_the_one_difference_and_the_page_is_one(
    client, db_session, kind, button
):
    email = f"knop-{kind}-1737@example.com"
    _household(db_session, kind, email)
    _sign_in(client, email)
    card = _card(client.get(HOUSEHOLD).text)
    other = RENEW if button == PAY else PAY
    assert f">{button}</a>" in card and other not in card, card[-600:]

    page = client.get(PAGE).text
    main = page[page.index('<main id="main"') : page.index("</main>")]
    assert "Lidmaatschap betalen · " in page[page.index("<title>") : page.index("</title>")]
    assert ">Lidmaatschap betalen</h1>" in main
    assert 'data-pay="Betalen"' in main and "Vernieuwen en betalen" not in main
    # #1747: the intro and the button of a transfer say what everyone does here.
    assert "Betaal het lidmaatschap voor je hele gezin." in main
    assert 'data-plain="Lidmaatschap aanvragen"' in main
    for old in ("Vernieuw het lidmaatschap", 'data-plain="Lidmaatschap vernieuwen"'):
        assert old not in main, old
    idle = main[main.index("data-save-idle") :]
    assert idle[idle.index(">") + 1 : idle.index("</span>")].strip() == "Betalen"

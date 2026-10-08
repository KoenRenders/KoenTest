"""Gezinsportaal toont een lopende vernieuwing i.p.v. het formulier (#618).

Na een vernieuwing via overschrijving verscheen bij een volgend bezoek opnieuw het
vernieuwformulier — en de knop liep gegarandeerd op de guard ("Je vernieuwing loopt
nog"). De server deed het juiste; het scherm nodigde uit tot een handeling die niet
kon slagen.

De invariant die telt: **guard en scherm zijn het altijd eens**. Beide stellen nu
dezelfde vraag via `open_renewal_payment()`.

Since #1590 renewing is its own page (`/leden/gezin/vernieuwen`), and that page
is where a running renewal stands instead of the form. "Mijn gezin" only says
how the membership stands: with a renewal running it points to that page and
offers no second renewal.

"The form is not there" is asked of the form itself (`id="vernieuw-form"`), not
of the words "Lidmaatschap vernieuwen": those are the page's title now, with or
without a form. And the last screen test is the other half — once the payment
is paid the form IS there — without which every "not there" above would also
pass on a page that never shows a form.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.membership.api import Membership, open_renewal_payment
from app.domains.payment.api import GatewayPayment, PaymentRecord
from tests.conftest import create_test_family

pytestmark = pytest.mark.ui_serverrendered

FORM = 'id="vernieuw-form"'
RENEW_PAGE = "/leden/gezin/vernieuwen"
HOUSEHOLD = "/leden/gezin"


def _login_as(client, email):
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _was_a_paid_member(db, member) -> None:
    """A renewal presupposes a membership that was paid before (#1730): without
    one this household would be paying its FIRST membership, with other words.
    Last year's, so it is not valid any more."""
    year = date.today().year - 1
    if db.query(Membership).filter_by(member_id=member.id, year=year).first() is None:
        db.add(
            Membership(
                member_id=member.id,
                year=year,
                is_active=True,
                valid_from=date(year, 1, 1),
                valid_to=date(year, 12, 31),
            )
        )
        db.flush()


def _openstaande_vernieuwing(db, member, method="transfer", gateway_payment_id=None):
    """Een niet-betaalde vernieuwing, zoals de renew-flow ze achterlaat."""
    _was_a_paid_member(db, member)
    jaar = date.today().year + 1
    ms = Membership(
        member_id=member.id,
        year=jaar,
        is_active=False,
        valid_from=date(jaar, 1, 1),
        valid_to=date(jaar, 12, 31),
    )
    db.add(ms)
    db.flush()
    rec = PaymentRecord(
        payable_type="membership",
        payable_id=ms.id,
        amount=Decimal("35.00"),
        method=method,
        status="pending",
        structured_communication="+++123/4567/89012+++",
        gateway_payment_id=gateway_payment_id,
    )
    db.add(rec)
    db.commit()
    return ms, rec


def test_overschrijving_toont_instructies_bij_een_verse_get(client, db_session):
    """De kern van #618: navigeren weg en terug mag het formulier niet terugbrengen."""
    member, _person = create_test_family(db_session, email="vern@example.com")
    _, rec = _openstaande_vernieuwing(db_session, member)
    _login_as(client, "vern@example.com")

    # #1641 (CR-11 Q79): the renewal page only starts a renewal; while one runs
    # it lands on Mijn gezin, whose Lidmaatschap card is the one place for it.
    answer = client.get(RENEW_PAGE, follow_redirects=False)
    assert answer.status_code == 303 and answer.headers["location"] == HOUSEHOLD
    html = client.get(HOUSEHOLD).text
    assert "+++123/4567/89012+++" in html
    # #1241: `35,00` en niet `35.00`. Deze regel legde de Amerikaanse notatie vast die
    # op de schermafdruk van de betaalinstructies opviel; het `geld`-filter (#735) doet
    # het bedrag nu zoals overal elders. Wat deze test hier bewaakt — dat het BEDRAG er
    # staat na een verse GET — verandert daar niet door.
    assert "35,00" in html
    assert "Vernieuwing geregistreerd" in html
    assert FORM not in html


def test_mijn_gezin_points_to_the_running_renewal_and_offers_no_second_one(client, db_session):
    """The portal page itself: a renewal that runs is a line with the way to the
    payment; without one the same card offers the renewal. A pair, so the
    missing button is the running renewal's doing."""
    member, _person = create_test_family(db_session, email="wijzer@example.com")
    _was_a_paid_member(db_session, member)
    db_session.commit()
    _login_as(client, "wijzer@example.com")
    button = 'href="/leden/gezin/vernieuwen"'

    before = client.get("/leden/gezin").text
    assert "Je vernieuwing loopt nog." not in before
    assert button in before and ">Lidmaatschap vernieuwen</a>" in before

    _openstaande_vernieuwing(db_session, member)
    after = client.get("/leden/gezin").text
    assert "Je vernieuwing loopt nog." in after
    # #1641: the card is the one place — no link to a second screen.
    assert "Bekijk de betaling" not in after and button not in after
    assert ">Lidmaatschap vernieuwen</a>" not in after, "a second renewal is offered"
    # #1632 (CR-11 Q73): what to pay stands in the card itself, not one click further.
    assert "+++123/4567/89012+++" in after, "the transfer to make is not in the card"


def test_afgebroken_online_betaling_toont_hervatknop(client, db_session):
    """#618-3: even doodlopend als de overschrijving, dus ook afgevangen."""
    member, _person = create_test_family(db_session, email="online@example.com")
    gw = GatewayPayment(
        amount=Decimal("35.00"),
        currency="EUR",
        status="open",
        provider="mollie",
        checkout_url="https://betaal.example/hervat",
    )
    db_session.add(gw)
    db_session.flush()
    _openstaande_vernieuwing(db_session, member, method="online", gateway_payment_id=gw.id)
    _login_as(client, "online@example.com")

    # #1641 (CR-11 Q79): the renewal page only starts a renewal; while one runs
    # it lands on Mijn gezin, whose Lidmaatschap card is the one place for it.
    answer = client.get(RENEW_PAGE, follow_redirects=False)
    assert answer.status_code == 303 and answer.headers["location"] == HOUSEHOLD
    html = client.get(HOUSEHOLD).text
    assert "Betaling hervatten" in html
    assert "https://betaal.example/hervat" in html
    assert FORM not in html


def test_online_zonder_checkout_url_toont_uitleg(client, db_session):
    member, _person = create_test_family(db_session, email="geenurl@example.com")
    _openstaande_vernieuwing(db_session, member, method="online")
    _login_as(client, "geenurl@example.com")

    # #1641 (CR-11 Q79): the renewal page only starts a renewal; while one runs
    # it lands on Mijn gezin, whose Lidmaatschap card is the one place for it.
    answer = client.get(RENEW_PAGE, follow_redirects=False)
    assert answer.status_code == 303 and answer.headers["location"] == HOUSEHOLD
    html = client.get(HOUSEHOLD).text
    assert "Je vernieuwing loopt nog" in html and "nog niet afgerond" in html
    assert "Betaling hervatten" not in html
    assert FORM not in html


def test_betaalde_vernieuwing_blokkeert_het_scherm_niet(client, db_session):
    """Zodra de betaling `paid` is, hoort het scherm weer normaal te zijn — precies
    zoals de guard dan weer doorlaat."""
    member, _person = create_test_family(db_session, email="betaald@example.com")
    _, rec = _openstaande_vernieuwing(db_session, member)
    rec.status = "paid"
    db_session.commit()
    _login_as(client, "betaald@example.com")

    html = client.get(RENEW_PAGE).text
    assert "+++123/4567/89012+++" not in html
    assert FORM in html, "a paid renewal still hides the form"


def test_guard_en_scherm_stellen_dezelfde_vraag(client, db_session):
    """Eén bron (#618-1): de functie die de guard gebruikt, voedt ook het scherm."""
    member, _person = create_test_family(db_session, email="bron@example.com")
    assert open_renewal_payment(db_session, member) is None

    _, rec = _openstaande_vernieuwing(db_session, member)
    assert open_renewal_payment(db_session, member).id == rec.id

    rec.status = "cancelled"
    db_session.commit()
    assert open_renewal_payment(db_session, member) is None


# ── The act itself: POST /leden/gezin/vernieuwen (#1590) ─────────────────────


def _renew(client, csrf, **data):
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    return client.post(RENEW_PAGE, data=data, headers=headers)


def _open_payments(db) -> int:
    db.expire_all()
    return db.query(PaymentRecord).filter(PaymentRecord.payable_type == "membership").count()


def test_a_renewal_without_a_payment_method_is_refused_at_that_field(client, db_session):
    """The banner alone, for the page's message line — and nothing booked."""
    create_test_family(db_session, email="geenkeuze@example.com")
    db_session.commit()
    csrf = _login_as(client, "geenkeuze@example.com")

    for data in ({}, {"payment_method": "cash"}):
        answer = _renew(client, csrf, **data)
        assert answer.status_code == 422, data
        assert answer.headers["HX-Retarget"] == "#vernieuw-melding"
        assert "<html" not in answer.text.lower() and "data-form-flow" not in answer.text
        assert 'data-error-for="payment_method"' in answer.text
        assert "Verzenden kan nog niet: controleer 1 veld." in answer.text
    assert _open_payments(db_session) == 0


def test_a_transfer_renewal_answers_the_page_with_what_to_pay(client, db_session):
    """#497: the payment details on the screen, from the booking itself — and
    the form is gone, because this renewal now runs (#618)."""
    member, _person = create_test_family(db_session, email="overschrijver@example.com")
    _was_a_paid_member(db_session, member)
    db_session.commit()
    csrf = _login_as(client, "overschrijver@example.com")

    answer = _renew(client, csrf, payment_method="transfer")

    assert answer.status_code == 200, answer.text[:300]
    # #1641: what to pay stands in the card of Mijn gezin; the answer goes
    # there with a hard redirect, as an online payment goes to its checkout.
    assert answer.headers["HX-Redirect"] == HOUSEHOLD and answer.text == ""
    db_session.expire_all()
    booked = db_session.query(PaymentRecord).filter_by(payable_type="membership").one()
    assert booked.method.value == "transfer" and booked.structured_communication
    html = client.get(HOUSEHOLD).text
    start = html.index("data-transfer-due")
    block = html[start : html.index("</ul>", start)]
    assert "Vernieuwing geregistreerd" in block
    assert booked.structured_communication in block
    assert f"€ {booked.amount:.2f}".replace(".", ",") in block
    assert FORM not in html


def test_a_second_renewal_is_refused_while_the_first_runs(client, db_session):
    """Guard and screen agree (#618): the screen shows no form, and whoever
    posts anyway is told why, in the banner, with nothing booked twice."""
    member, _person = create_test_family(db_session, email="tweemaal@example.com")
    _openstaande_vernieuwing(db_session, member)
    csrf = _login_as(client, "tweemaal@example.com")

    answer = _renew(client, csrf, payment_method="transfer")

    assert answer.status_code == 422
    assert answer.headers["HX-Retarget"] == "#vernieuw-melding"
    assert "Verzenden is niet gelukt." in answer.text
    assert "data-error-for" not in answer.text, "this refusal has no field"
    assert "<html" not in answer.text.lower()
    assert _open_payments(db_session) == 1


def test_an_online_renewal_leaves_with_a_hard_redirect(client, db_session, mock_mollie):
    """The fixed decision: `HX-Redirect` to the provider, never a soft swap."""
    create_test_family(db_session, email="onlinebetaler@example.com")
    db_session.commit()
    csrf = _login_as(client, "onlinebetaler@example.com")

    answer = _renew(client, csrf, payment_method="online")

    assert answer.status_code == 200, answer.text[:300]
    assert answer.headers["HX-Redirect"] == "https://mollie.test/checkout/tr_test_123"
    assert answer.text == ""


def test_the_renewal_needs_a_session_and_the_csrf_token(client, db_session):
    create_test_family(db_session, email="zondertoken@example.com")
    db_session.commit()
    assert _renew(client, None, payment_method="transfer").status_code == 401, "no session"
    _login_as(client, "zondertoken@example.com")
    assert _renew(client, None, payment_method="transfer").status_code == 403, "no token"
    assert _open_payments(db_session) == 0

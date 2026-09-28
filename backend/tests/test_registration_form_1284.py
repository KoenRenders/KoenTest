"""One registration form for the public and for the board (#1284).

Koen, validating #1192 on HDEV: the board's form showed no amounts. It was a
second form beside the public one — its own context, its own processing, its own
fields — and it had not followed the first. He decided: "100% gelijk aan het
publieke formulier, met uitzondering van de terugroutering en de producten die
enkel in de backoffice zichtbaar zijn".

So there is one context builder, one total and one processing
(`activities/registration_form.py`), and one template for the fields
(`_inschrijf_velden.html`). These tests send the same cases through both
channels, over HTTP, and expect only the differences the issue lists:

| | public | board |
|---|---|---|
| who registers | the signed-in person | the person of the typed address |
| after a free or transfer registration | the confirmation fragment | the registration in the back office |
| after Mollie | the public return page | the registration in the back office |
| products | publicly bookable | also back-office-only ones, badged |

Broken on purpose (28 September 2026), one violation at a time:

| Violation | Failed |
|---|---|
| the board saves no person (`person_id = None`) | the member pays the member price [board]; shown = charged for a member [board] |
| the public channel looks up the TYPED address | the public form never prices by the typed address |
| the board returns from Mollie to the public page | Mollie returns each channel to its own page [board] |
| a field added to the board page only | both channels render the same fields |
| the board shown only publicly bookable products | a back-office product is offered to the board only |
| the board's price refresh ignoring the typed address | the board rows follow the typed member address |
| the board's price refresh not carrying the quantities | the same test, on "the entered quantity was lost" |
| the public channel given a price refresh too | only the board refreshes prices on the address |
"""
import re
from datetime import date
from decimal import Decimal

import pytest

from app.domains.activities.api import Registration
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

MEMBER = "lid-1284@example.org"
OTHER = "gast-1284@example.org"
CHANNELS = ["public", "board"]


@pytest.fixture(autouse=True)
def _limits():
    from app.limiter import registration_limiter

    registration_limiter._calls.clear()
    yield
    registration_limiter._calls.clear()


@pytest.fixture
def member(db_session):
    from app.domains.membership.api import Membership

    household, person = create_test_family(db_session, email=MEMBER)
    year = date.today().year
    db_session.add(Membership(member_id=household.id, year=year, is_active=True,
                              valid_from=date(year, 1, 1), valid_to=date(year, 12, 31)))
    db_session.flush()
    return person


@pytest.fixture
def paid(db_session):
    """Ten euro, six for members."""
    activity, component, product = seed_activity_with_product(db_session, price="10.00")
    product.member_price = Decimal("6.00")
    db_session.flush()
    return activity, component, product


@pytest.fixture
def free(db_session):
    return seed_activity_with_product(db_session, price="0", is_free=True)


def _send(client, channel: str, act, data: dict, *, visitor_email: str | None = None):
    """POST the form through one channel. `visitor_email` is who is signed in on
    the public side; the board is always the seeded admin."""
    activity, component, product = act
    if channel == "public":
        client.cookies.clear()
        if visitor_email:
            client.cookies.set(SESSION_COOKIE, make_session_value(visitor_email))
        return client.post(f"/activiteiten/{activity.id}/inschrijven/{component.id}",
                           data=data, headers={"HX-Request": "true"})
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return client.post(f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw",
                       data={"onderdeel": str(component.id), **data},
                       headers={"HX-Request": "true", "X-CSRF-Token": csrf_token_for(value)})


def _form(act, *, email: str, quantity: int = 1, method: str = "transfer") -> dict:
    return {"contact_name": "Deelnemer 1284", "contact_email": email, "phone": "0470000000",
            f"product_{act[2].id}": str(quantity), "payment_method": method}


def _saved(db, act) -> list:
    return db.query(Registration).filter(Registration.activity_id == act[0].id).all()


def _charged(db, registration) -> Decimal | None:
    from app.domains.payment.api import PayableType, PaymentRecord

    record = db.query(PaymentRecord).filter(
        PaymentRecord.payable_type == PayableType.REGISTRATION,
        PaymentRecord.payable_id == registration.id).one_or_none()
    return record.amount if record else None


def _landed(channel, resp, registration) -> None:
    """Where each channel lands after a registration without Mollie."""
    if channel == "public":
        assert "Je inschrijving is ontvangen" in resp.text, resp.text[:300]
        assert resp.headers.get("HX-Redirect") is None
    else:
        assert resp.headers.get("HX-Redirect") == f"/admin/inschrijvingen/{registration.id}"


# ── The same cases through both channels ──────────────────────────────────────

@pytest.mark.parametrize("channel", CHANNELS)
def test_a_free_registration(client, db_session, free, channel):
    resp = _send(client, channel, free, _form(free, email=OTHER))
    [reg] = _saved(db_session, free)
    _landed(channel, resp, reg)
    assert _charged(db_session, reg) is None


@pytest.mark.parametrize("channel", CHANNELS)
def test_a_paid_registration_by_transfer_for_a_non_member(client, db_session, paid, channel):
    resp = _send(client, channel, paid, _form(paid, email=OTHER))
    [reg] = _saved(db_session, paid)
    _landed(channel, resp, reg)
    assert _charged(db_session, reg) == Decimal("10.00")
    assert reg.person_id is None


@pytest.mark.parametrize("channel", CHANNELS)
def test_a_member_pays_the_member_price(client, db_session, paid, member, channel):
    """Public: the member is signed in. Board: the board types the member's
    address. Either way the registration hangs on the member and is charged the
    member price."""
    resp = _send(client, channel, paid, _form(paid, email=MEMBER), visitor_email=MEMBER)
    [reg] = _saved(db_session, paid)
    _landed(channel, resp, reg)
    assert reg.person_id == member.id
    assert _charged(db_session, reg) == Decimal("6.00")


@pytest.mark.parametrize("channel", CHANNELS)
def test_online_goes_to_mollie(client, db_session, paid, channel, mock_mollie):
    resp = _send(client, channel, paid, _form(paid, email=OTHER, method="online"))
    assert resp.headers.get("HX-Redirect") == "https://mollie.test/checkout/tr_test_123"
    assert len(_saved(db_session, paid)) == 1


@pytest.mark.parametrize("channel", CHANNELS)
def test_no_product_chosen_is_refused(client, db_session, paid, channel):
    resp = _send(client, channel, paid, _form(paid, email=OTHER, quantity=0))
    assert "Selecteer minstens één product." in resp.text
    assert _saved(db_session, paid) == []


@pytest.mark.parametrize("channel", CHANNELS)
def test_an_invalid_address_is_refused(client, db_session, paid, channel):
    resp = _send(client, channel, paid, _form(paid, email="iemand@"))
    assert "Dat e-mailadres is niet geldig." in resp.text, resp.text[:300]
    assert _saved(db_session, paid) == []


# ── Shown and charged are the same amount ─────────────────────────────────────

@pytest.mark.parametrize("channel", CHANNELS)
@pytest.mark.parametrize("who", [MEMBER, OTHER])
def test_the_total_shown_is_the_amount_charged(client, db_session, paid, member, channel, who):
    """The form prices through `form_context`/`total_context`; the charge through
    `compute_registration_total`, by `registration.person`. If the board showed
    the typed member's price but saved no person, the two would differ."""
    activity, component, product = paid
    data = _form(paid, email=who, quantity=2)
    if channel == "public":
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, make_session_value(who))
        url = f"/activiteiten/{activity.id}/inschrijven/{component.id}/totaal"
        shown = client.post(url, data=data).text
    else:
        value = make_session_value(SEEDED_ADMIN_EMAIL)
        client.cookies.set(SESSION_COOKIE, value)
        shown = client.post(f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw/totaal",
                            data={"onderdeel": str(component.id), **data},
                            headers={"X-CSRF-Token": csrf_token_for(value)}).text
    amount = re.search(r"€\s*([\d.,]+)", shown).group(1)
    shown_total = Decimal(amount.replace(".", "").replace(",", "."))

    _send(client, channel, paid, data, visitor_email=who)
    [reg] = _saved(db_session, paid)
    assert shown_total == _charged(db_session, reg) == (
        Decimal("12.00") if who == MEMBER else Decimal("20.00"))


# ── The channel-specific differences, and only those ──────────────────────────

def _field_names(html: str) -> set[str]:
    return set(re.findall(r'<(?:input|select|textarea)[^>]*\sname="([^"]+)"', html))


def test_both_channels_render_the_same_fields(client, db_session, paid):
    """One template for the fields: a field in one channel and not in the other
    is red, unless it is a difference the issue names (the board's CSRF token and
    its component choice)."""
    activity, component, product = paid
    client.cookies.clear()
    public = client.get(f"/activiteiten/{activity.id}/inschrijven/{component.id}").text
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    board = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw").text
    board_form = board[board.index('id="inschrijving-nieuw-form"'):]

    public_fields = _field_names(public)
    assert {"contact_name", "contact_email", "phone", "payment_method",
            f"product_{product.id}"} <= public_fields, public_fields
    assert _field_names(board_form) - {"csrf_token", "onderdeel"} == public_fields


def test_the_board_sees_prices_a_total_and_online(client, db_session, paid):
    activity, component, product = paid
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    page = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw").text
    assert "€10,00" in page, "no price per product"
    assert "Totaal:" in page, "no total"
    assert 'name="payment_method" value="online"' in page, "no online payment"


def test_a_back_office_product_is_offered_to_the_board_only(client, db_session, paid):
    from app.domains.activities.api import ActivityProduct

    activity, component, product = paid
    hidden = ActivityProduct(component_id=component.id, name="Enkel bestuur",
                             price=Decimal("5.00"), is_free=False, is_active=False)
    db_session.add(hidden)
    db_session.flush()
    client.cookies.clear()
    public = client.get(f"/activiteiten/{activity.id}/inschrijven/{component.id}").text
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    board = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw").text
    assert f'name="product_{hidden.id}"' not in public
    assert f'name="product_{hidden.id}"' in board and "niet publiek" in board


@pytest.mark.parametrize("channel, back", [
    ("public", "/betaling/succes?registration={id}"),
    ("board", "/admin/inschrijvingen/{id}")])
def test_mollie_returns_each_channel_to_its_own_page(client, db_session, paid, channel,
                                                     back, monkeypatch):
    from app.domains.payment.providers import mollie
    from app.domains.payment.providers.base import PaymentResult

    seen: dict = {}

    def fake_create_payment(self, amount, description, redirect_url, webhook_url, metadata):
        seen["redirect_url"] = redirect_url
        return PaymentResult(provider_payment_id="tr_1284", status="pending",
                             checkout_url="https://mollie.test/checkout/tr_1284")

    monkeypatch.setattr(mollie.MollieProvider, "create_payment", fake_create_payment)
    _send(client, channel, paid, _form(paid, email=OTHER, method="online"))
    [reg] = _saved(db_session, paid)
    assert seen["redirect_url"].endswith(back.format(id=reg.id)), seen["redirect_url"]


def test_the_public_form_never_prices_by_the_typed_address(client, db_session, paid, member):
    """The security half of "who registers": nobody signed in, a member's address
    typed into the public form. Looking that address up would give anyone the
    member price; the public channel takes its person from the session only."""
    resp = _send(client, "public", paid, _form(paid, email=MEMBER))
    [reg] = _saved(db_session, paid)
    _landed("public", resp, reg)
    assert reg.person_id is None
    assert _charged(db_session, reg) == Decimal("10.00")


# ── Koen's answer: the board's rows follow the typed member address ──────────

def _board_prices(client, act, email: str, quantity: int) -> str:
    activity, component, product = act
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return client.post(
        f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw/prijzen",
        data={"onderdeel": str(component.id), "contact_email": email,
              f"product_{product.id}": str(quantity)},
        headers={"X-CSRF-Token": csrf_token_for(value)}).text


def test_the_board_rows_follow_the_typed_member_address(client, db_session, paid, member):
    """Rows and total come back together, as the public form shows them to a
    signed-in member — and with the quantity that was entered, not the opening
    one: the block is swapped, the fields around it are not."""
    product = paid[2]
    for_member = _board_prices(client, paid, MEMBER, 2)
    assert "€10,00 / leden €6,00" in for_member, for_member[:600]
    assert "€12,00" in for_member and "ledenprijs" in for_member
    assert re.search(rf'name="product_{product.id}"[^>]*value="2"', for_member), (
        "the entered quantity was lost in the refresh")
    assert 'name="contact_email"' not in for_member, "the address field is part of the swap"

    for_guest = _board_prices(client, paid, OTHER, 2)
    assert "/ leden" not in for_guest and "€20,00" in for_guest


def test_only_the_board_refreshes_prices_on_the_address(client, db_session, paid):
    activity, component, _product = paid
    client.cookies.clear()
    public = client.get(f"/activiteiten/{activity.id}/inschrijven/{component.id}").text
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    board = client.get(f"/admin/activiteiten/{activity.id}/inschrijvingen/nieuw").text
    assert "/prijzen" not in public
    assert f'hx-post="/admin/activiteiten/{activity.id}/inschrijvingen/nieuw/prijzen"' in board
    assert f'hx-target="#prijsblok-{component.id}"' in board

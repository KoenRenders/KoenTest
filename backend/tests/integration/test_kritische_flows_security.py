"""Regressietests voor drie geld-/autorisatie-invarianten op de kritische flows
(#599, onder de audits #530/#529). Scope: enkel vastnagelen dat de invarianten
houden — geen gedragswijziging aan de productiecode.

1. IDOR op het gezinsportaal: een lid mag geen persoon van een ánder gezin
   bewerken. Since CR-13 phase 4b (#1251) the one door is the save of Mijn
   gezin, which knows only the persons of the member's own household.
2. De Mollie-webhook is onvervalsbaar: status/bedrag komen uitsluitend uit de
   re-fetch bij Mollie, nooit uit de (ongesigneerde) POST-body.
3. De echte `MollieProvider.create_payment` bouwt de juiste payload en slaat de
   webhookUrl over op localhost — de buitenste geldgrens, die elders gemockt is.
"""

from decimal import Decimal

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.payment.api import PaymentStatus
from tests.conftest import create_test_family, household_fields


def _signed_in(client, email: str) -> dict:
    """The member's session on the site, and the CSRF header its forms send."""
    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


# ── 1. IDOR gezinsportaal ────────────────────────────────────────────────────


def test_gezinsportaal_idor_blokkeert_bewerken_vreemd_gezin(client, db_session):
    """A member of household A cannot change a person of household B: the save of
    Mijn gezin refuses a row that carries a stranger's id, and nothing is written.

    There is no door left that removes a person by id (the JSON doors went with
    CR-13 phase 4b, #1251): the save removes who the form no longer has, and only
    from the member's own household — `test_a_person_of_another_household_is_not_touched`
    in `mdm/tests/test_household_save.py`.

    Proven red by letting `_save_person` look the row's id up among all persons
    instead of the household's own: 200, and the stranger is called "Gekaapt".
    """
    from app.domains.mdm.api import Person

    create_test_family(db_session, email="idor-a@example.com", mobile="0470 00 00 01")
    _mem_b, pers_b = create_test_family(db_session, email="idor-b@example.com")
    db_session.commit()
    original = pers_b.first_name

    headers = _signed_in(client, "idor-a@example.com")
    fields = household_fields(client)
    fields["h_order"] = [*fields["h_order"], str(pers_b.id)]
    fields[f"h.{pers_b.id}.first_name"] = "Gekaapt"
    fields[f"h.{pers_b.id}.last_name"] = pers_b.last_name

    resp = client.post("/leden/gezin", data=fields, headers=headers)

    assert resp.status_code == 422, resp.text[:300]
    assert "hoort niet meer bij het gezin" in resp.text, resp.text[:300]
    db_session.expire_all()
    assert db_session.get(Person, pers_b.id).first_name == original


# ── 2. Webhook-onvervalsbaarheid ─────────────────────────────────────────────


def _seed_gateway_payment(db, amount="35.00", status="pending"):
    from app.domains.payment.api import GatewayPayment

    gp = GatewayPayment(
        provider="mollie",
        provider_payment_id="tr_forge_1",
        amount=Decimal(amount),
        status=status,
        checkout_url="https://mollie.test/checkout/tr_forge_1",
        description="Test",
        payment_metadata={},
    )
    db.add(gp)
    db.flush()
    return gp


def test_webhook_negeert_vervalste_status_en_bedrag(client, db_session, monkeypatch):
    """De webhook-body is ongesigneerd en forgeerbaar. Ook al post iemand
    `status=paid&amount=999`, de status komt enkel uit de re-fetch bij Mollie —
    die hier 'pending' teruggeeft, dus de betaling blijft 'pending'."""
    from app.limiter import mollie_webhook_limiter

    mollie_webhook_limiter._calls.clear()
    from app.domains.payment.providers import mollie
    from app.domains.payment.providers.base import PaymentStatusResult

    monkeypatch.setattr(
        mollie.MollieProvider,
        "get_payment_details",
        lambda self, pid: PaymentStatusResult(status="pending", amount=None, currency=None),
    )

    gp = _seed_gateway_payment(db_session, status="pending")

    resp = client.post(
        "/api/v1/payment-gateway/webhooks/mollie",
        data={"id": "tr_forge_1", "status": "paid", "amount": "999.00"},
    )
    assert resp.status_code == 200
    db_session.expire_all()
    from app.domains.payment.api import GatewayPayment

    # Mollie's own vocabulary on this column (§B4.10): a bare string, not a member.
    assert db_session.get(GatewayPayment, gp.id).status == PaymentStatus.PENDING.value


def test_webhook_onbekende_id_wordt_genegeerd(client, db_session):
    """Een onbekend payment-id verandert niets → 200 {'status': 'ignored'}."""
    from app.limiter import mollie_webhook_limiter

    mollie_webhook_limiter._calls.clear()

    resp = client.post(
        "/api/v1/payment-gateway/webhooks/mollie",
        data={"id": "tr_bestaat_niet"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}


# ── 3. Echte MollieProvider.create_payment ───────────────────────────────────


class _FakeResponse:
    def __init__(self, *, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self.is_success:
            raise AssertionError("raise_for_status na is_success-check")


_OK_JSON = {
    "id": "tr_live_1",
    "status": "open",
    "_links": {"checkout": {"href": "https://mollie.test/checkout/tr_live_1"}},
}


def test_create_payment_payload_en_localhost_webhook_skip(monkeypatch):
    """Buitenste geldgrens: bedrag als 2-decimalen EUR-string, en op een lokale
    webhook-URL wordt `webhookUrl` weggelaten (Mollie kan localhost niet bereiken)."""
    from app.domains.payment.providers import mollie

    captured: dict = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["payload"] = json
        return _FakeResponse(json_data=_OK_JSON)

    monkeypatch.setattr(mollie.httpx, "post", fake_post)

    provider = mollie.MollieProvider(api_key="test_key")
    result = provider.create_payment(
        amount=Decimal("12"),
        description="Test",
        redirect_url="https://raak.example/ok",
        webhook_url="http://localhost:8000/api/v1/payment-gateway/webhooks/mollie",
        metadata={"ref": 1},
    )

    assert captured["payload"]["amount"] == {"currency": "EUR", "value": "12.00"}
    assert "webhookUrl" not in captured["payload"]  # localhost overgeslagen
    assert result.provider_payment_id == "tr_live_1"
    # `PaymentResult` is the adapter boundary: it carries our code as a string.
    assert result.status == PaymentStatus.PENDING.value  # 'open' → intern 'pending'


def test_create_payment_stuurt_webhook_op_echte_host(monkeypatch):
    from app.domains.payment.providers import mollie

    captured: dict = {}
    monkeypatch.setattr(
        mollie.httpx,
        "post",
        lambda url, json, headers, timeout: (
            captured.update(payload=json) or _FakeResponse(json_data=_OK_JSON)
        ),
    )

    provider = mollie.MollieProvider(api_key="test_key")
    provider.create_payment(
        amount=Decimal("35.00"),
        description="Test",
        redirect_url="https://raak.example/ok",
        webhook_url="https://raak.example/api/v1/payment-gateway/webhooks/mollie",
        metadata={},
    )
    assert (
        captured["payload"]["webhookUrl"]
        == "https://raak.example/api/v1/payment-gateway/webhooks/mollie"
    )


def test_create_payment_faalt_bij_niet_200(monkeypatch):
    """Een niet-200 van Mollie → nette ValueError i.p.v. een stille 'paid'."""
    from app.domains.payment.providers import mollie

    monkeypatch.setattr(
        mollie.httpx,
        "post",
        lambda url, json, headers, timeout: _FakeResponse(status_code=422, text="Unprocessable"),
    )
    provider = mollie.MollieProvider(api_key="test_key")
    with pytest.raises(ValueError):
        provider.create_payment(
            amount=Decimal("10.00"),
            description="Test",
            redirect_url="https://raak.example/ok",
            webhook_url="https://raak.example/hook",
            metadata={},
        )


def test_create_payment_zonder_api_key_faalt():
    from app.domains.payment.providers import mollie

    provider = mollie.MollieProvider(api_key="")
    with pytest.raises(ValueError):
        provider.create_payment(
            amount=Decimal("10.00"),
            description="Test",
            redirect_url="https://raak.example/ok",
            webhook_url="https://raak.example/hook",
            metadata={},
        )

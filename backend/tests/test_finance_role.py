"""FINANCE-rol: financiële scheiding penningmeester vs. admin (#207).

Enkel FINANCE mag betalingen invullen, bewerken, terugbetalen of verwijderen.
ADMIN mag betalingen wél inkijken (lijst, saldo) maar niet muteren. De rol wordt
in migratie 056 toegekend aan koen.renders@gmail.com en steven.paepen@ik.me;
kris.vandenbosch@raakvzw.be heeft enkel ADMIN en is dus de admin-only testcase.
"""
from decimal import Decimal

from app.domains.auth.api import create_access_token, get_user_roles
from app.domains.payment.api import PaymentRecord

FINANCE_EMAIL = "koen.renders@gmail.com"      # ADMIN + FINANCE (014 + 056)
ADMIN_ONLY_EMAIL = "kris.vandenbosch@raakvzw.be"  # enkel ADMIN (014)


def _headers(email):
    return {"Authorization": f"Bearer {create_access_token({'sub': email})}"}


def _seed_charge(db, *, payable_id=1, amount="18.00", amount_paid="18.00", status="paid"):
    charge = PaymentRecord(
        payable_type="registration", payable_id=payable_id,
        amount=Decimal(amount),
        amount_paid=Decimal(amount_paid) if amount_paid is not None else None,
        method="transfer", status=status, type="charge",
    )
    db.add(charge)
    db.flush()
    return charge


def test_finance_role_seeded_for_treasurers_only(db_session):
    assert "FINANCE" in get_user_roles(db_session, FINANCE_EMAIL)
    assert "FINANCE" not in get_user_roles(db_session, ADMIN_ONLY_EMAIL)
    assert "ADMIN" in get_user_roles(db_session, ADMIN_ONLY_EMAIL)


def test_auth_me_reports_is_finance(client):
    fin = client.get("/api/v1/auth/me", headers=_headers(FINANCE_EMAIL)).json()
    assert fin["is_finance"] is True and fin["is_admin"] is True

    adm = client.get("/api/v1/auth/me", headers=_headers(ADMIN_ONLY_EMAIL)).json()
    assert adm["is_finance"] is False and adm["is_admin"] is True


def test_admin_may_view_payments(client, db_session):
    """Een admin zonder FINANCE mag betalingen wél inkijken."""
    _seed_charge(db_session)
    resp = client.get("/api/v1/payment-status/records", headers=_headers(ADMIN_ONLY_EMAIL))
    assert resp.status_code == 200, resp.text


def test_admin_without_finance_cannot_mutate(client, db_session):
    """Admin zonder FINANCE krijgt 403 op elke mutatie (bewerken/refund/verwijderen)."""
    charge = _seed_charge(db_session)
    h = _headers(ADMIN_ONLY_EMAIL)

    patch = client.patch(f"/api/v1/payment-status/records/{charge.id}",
                         json={"status": "paid", "amount_paid": "18.00"}, headers=h)
    assert patch.status_code == 403, patch.text

    refund = client.post(f"/api/v1/payment-status/records/{charge.id}/refund",
                         json={"amount": "5.00"}, headers=h)
    assert refund.status_code == 403, refund.text

    delete = client.delete(f"/api/v1/payment-status/records/{charge.id}", headers=h)
    assert delete.status_code == 403, delete.text


def test_finance_may_mutate(client, db_session):
    """FINANCE mag wél een terugbetaling registreren."""
    charge = _seed_charge(db_session)
    resp = client.post(f"/api/v1/payment-status/records/{charge.id}/refund",
                       json={"amount": "18.00"}, headers=_headers(FINANCE_EMAIL))
    assert resp.status_code == 200, resp.text
    assert resp.json()["type"] == "refund"


def test_editing_amount_paid_stamps_paid_at(client, db_session):
    """#346: een ontvangen bedrag invullen via het bewerk-endpoint zet meteen
    paid_at, zodat er geen 'betaald zonder datum'-record ontstaat."""
    charge = _seed_charge(db_session, amount="18.00", amount_paid=None, status="pending")
    assert charge.paid_at is None
    resp = client.patch(f"/api/v1/payment-status/records/{charge.id}",
                        json={"amount_paid": "18.00"}, headers=_headers(FINANCE_EMAIL))
    assert resp.status_code == 200, resp.text
    db_session.refresh(charge)
    assert charge.paid_at is not None

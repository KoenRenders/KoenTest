"""FINANCE-rol: financiële scheiding penningmeester vs. admin (#207).

Enkel FINANCE mag betalingen invullen, bewerken, terugbetalen of verwijderen.
ADMIN mag betalingen wél inkijken (lijst, saldo) maar niet muteren. De rol wordt
in migratie 056 toegekend aan de twee penningmeester-zetels; de derde zetel uit
014 heeft enkel ADMIN en is dus de admin-only testcase. De adressen hieronder zijn
de placeholder-defaults van SEED_ADMIN_EMAILS/SEED_FINANCE_EMAILS.
"""

from decimal import Decimal

from app.domains.auth.api import create_access_token, get_user_roles
from app.domains.payment.api import PaymentRecord
from tests import payments_door

FINANCE_EMAIL = "beheerder@example.com"  # ADMIN + FINANCE (014 + 056)
ADMIN_ONLY_EMAIL = "bestuurslid@example.com"  # enkel ADMIN (014)


def _headers(email):
    return {"Authorization": f"Bearer {create_access_token({'sub': email})}"}


def _seed_charge(db, *, payable_id=1, amount="18.00", amount_paid="18.00", status="paid"):
    charge = PaymentRecord(
        payable_type="registration",
        payable_id=payable_id,
        amount=Decimal(amount),
        amount_paid=Decimal(amount_paid) if amount_paid is not None else None,
        method="transfer",
        status=status,
        type="charge",
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


def test_editing_amount_paid_stamps_paid_at(client, db_session):
    """#346: een ontvangen bedrag invullen via het bewerk-endpoint zet meteen
    paid_at, zodat er geen 'betaald zonder datum'-record ontstaat."""
    charge = _seed_charge(db_session, amount="18.00", amount_paid=None, status="pending")
    assert charge.paid_at is None
    resp = payments_door.update(client, charge.id, {"amount_paid": "18.00"}, actor=FINANCE_EMAIL)
    assert resp.status_code == 200, resp.text
    db_session.refresh(charge)
    assert charge.paid_at is not None

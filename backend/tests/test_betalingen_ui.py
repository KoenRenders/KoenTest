"""Fase 3b (#401): server-rendered betalingen-scherm — matrix, FINANCE-refunds,
bevestigen en export (sessie + CSRF)."""
from decimal import Decimal

from tests.conftest import SEEDED_ADMIN_EMAIL
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.payment.api import PaymentRecord


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _make_finance(db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
        db.flush()


def _record(db, amount="25.00", status="pending", payable_id=1):
    rec = PaymentRecord(payable_type="membership", payable_id=payable_id,
                        amount=Decimal(amount), method="transfer", status=status)
    db.add(rec)
    db.flush()
    return rec


def test_betalingen_requires_session(client):
    assert client.get("/admin/betalingen").status_code == 401


def test_betalingen_matrix_filters_and_totals(client, db_session):
    _record(db_session, amount="25.00", status="pending")
    _login(client)
    page = client.get("/admin/betalingen")
    assert page.status_code == 200 and "25.00" in page.text

    gefilterd = client.get("/admin/betalingen/lijst?status=paid")
    assert "Geen betalingen voor deze filter" in gefilterd.text or "25.00" not in gefilterd.text


def test_bevestigen_is_finance_only(client, db_session):
    rec = _record(db_session)
    # Een admin ZONDER FINANCE-rol → 403 (financiële scheiding, #83).
    alleen_admin = User(email="alleen-admin@example.com", is_active=True)
    db_session.add(alleen_admin)
    db_session.flush()
    db_session.add(UserRole(user_id=alleen_admin.id, role_code="ADMIN"))
    db_session.flush()
    value = make_session_value("alleen-admin@example.com")
    client.cookies.set(SESSION_COOKIE, value)
    csrf = csrf_token_for(value)
    resp = client.post(f"/admin/betalingen/{rec.id}/bevestigen",
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 403

    # Met FINANCE (de geseede beheerder) lukt het wel.
    _make_finance(db_session)
    csrf = _login(client)
    ok = client.post(f"/admin/betalingen/{rec.id}/bevestigen",
                     headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200
    db_session.expire_all()
    assert rec.status == "paid" and rec.amount_paid == Decimal("25.00")


def test_refund_via_scherm(client, db_session):
    rec = _record(db_session, status="paid")
    rec.amount_paid = Decimal("25.00")
    db_session.flush()
    _make_finance(db_session)
    csrf = _login(client)

    resp = client.post(f"/admin/betalingen/{rec.id}/refund",
                       data={"amount": "10,00", "note": "Deels terug"},
                       headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    refund = (db_session.query(PaymentRecord)
              .filter(PaymentRecord.refund_of_id == rec.id).one())
    assert refund.type == "refund" and refund.amount == Decimal("-10.00")

    # Meer terugbetalen dan netto ontvangen → nette 400 uit de servicelaag.
    fout = client.post(f"/admin/betalingen/{rec.id}/refund",
                       data={"amount": "1000"},
                       headers={"X-CSRF-Token": csrf})
    assert fout.status_code == 400


def test_export_downloads_ods(client, db_session):
    _record(db_session)
    _login(client)
    resp = client.get("/admin/betalingen/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/vnd.oasis")

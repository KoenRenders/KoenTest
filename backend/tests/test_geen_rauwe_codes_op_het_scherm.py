"""Geen rauwe DB-waarden op de beheerschermen (#630, §2.12).

De gate-regels vangen dit statisch; deze twee tests kijken naar de gerenderde output,
want dát is waar de code zichtbaar werd.
"""
from decimal import Decimal

import pytest

from app.domains.auth.api import (SESSION_COOKIE, User, UserRole, make_session_value)
from app.domains.payment.api import PaymentRecord
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

# Wat er tot #630 letterlijk op het scherm stond.
RAUW = ("payment.webhook_mismatch", "mail.definitief_gefaald", "kernel.job_gefaald",
        ">online<", ">transfer<", ">cash<")


def _login(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    for rol in ("FINANCE", "OPERATOR"):
        if not any(r.role_code == rol for r in user.roles):
            db.add(UserRole(user_id=user.id, role_code=rol))
    db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def test_betalingen_toont_geen_rauwe_codes(client, db_session):
    db_session.add(PaymentRecord(
        payable_type="registration", payable_id=9911, type="charge",
        amount=Decimal("10.00"), amount_paid=Decimal("10.00"),
        method="transfer", status="paid"))
    db_session.commit()
    _login(client, db_session)

    html = client.get("/admin/betalingen/lijst").text
    assert "Overschrijving" in html, "de betaalwijze hoort leesbaar te zijn"
    for code in RAUW:
        assert code not in html, f"rauwe code {code!r} op het scherm"


def test_onbekende_status_valt_terug_op_leesbare_tekst(client, db_session):
    """Mollie kent ook `open`, `authorized` en `expired`; die vielen door naar de
    fallback en toonden een Engelse code als badge. Een tijdbom, geen bug."""
    db_session.add(PaymentRecord(
        payable_type="registration", payable_id=9912, type="charge",
        amount=Decimal("10.00"), method="online", status="authorized"))
    db_session.commit()
    _login(client, db_session)

    html = client.get("/admin/betalingen/lijst").text
    assert ">authorized<" not in html
    assert "Onbekende status" in html


def test_werkbank_toont_geen_interne_taakcodes(client, db_session):
    """`task.kind` is een intern dotted veld dat als badge op élke taak stond."""
    _login(client, db_session)
    html = client.get("/admin/werkbank").text
    for code in ("payment.webhook_mismatch", "mail.definitief_gefaald",
                 "kernel.job_gefaald"):
        assert code not in html, f"intern taaktype {code!r} op het scherm"

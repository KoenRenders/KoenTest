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
        if not any(r.role_code.value == rol for r in user.roles):
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


def test_an_unknown_status_no_longer_reaches_the_column(client, db_session):
    """Mollie also knows `open`, `authorized` and `expired`.

    Until CR-12 phase 1 those fell through to the fallback and showed an English
    code as a badge; this test then proved that the fallback was readable. Since
    the code list that is no longer the question: `authorized` can no longer be
    in `payment_records.status`. The enum rejects it in Python and the foreign
    key rejects it in the database, and that is a stronger promise than a tidy
    fallback.

    The concern itself has not gone away, it has moved: Mollie's words come in
    on `gateway_payments.status` — deliberately without a code table (§B4.10) —
    and `providers/mollie.py` translates them into ours, with an explicit branch
    for the value it does not know.
    """
    from app.domains.payment.api import PayableType, PaymentStatus, PaymentType
    from app.domains.mdm.api import PaymentMethod

    with pytest.raises(ValueError) as excinfo:
        PaymentRecord(
            payable_type=PayableType.REGISTRATION, payable_id=9912,
            type=PaymentType.CHARGE, amount=Decimal("10.00"),
            method=PaymentMethod.ONLINE, status="authorized")
    assert "authorized" in str(excinfo.value)
    assert "PaymentStatus" in str(excinfo.value)


def test_werkbank_toont_geen_interne_taakcodes(client, db_session):
    """`task.kind` is een intern dotted veld dat als badge op élke taak stond."""
    _login(client, db_session)
    html = client.get("/admin/werkbank").text
    for code in ("payment.webhook_mismatch", "mail.definitief_gefaald",
                 "kernel.job_gefaald"):
        assert code not in html, f"intern taaktype {code!r} op het scherm"

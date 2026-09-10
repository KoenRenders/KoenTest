"""The flat dataset download (#832, point 5).

Phase 1 has no screen and no menu item — that is #833 — but it does ship one
download per fact, so the datasets are usable in LibreOffice Calc before the panel
exists.

**The door is `require_admin_ui`, and it is the whole fence** (#832, decision of
10 September 2026): v2.3.0 adds no new security surface, so reporting sits behind
the same door as every other admin screen and a FINANCE-only user does not reach
it. The roles the universe declares per object are not enforced. What has to hold
here is therefore the door — no session, wrong role, right role — and the tenant
filter on what comes out.
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from app.domains.auth.api import (
    SESSION_COOKIE, User, UserRole, make_session_value,
)
from tests._reporting_seed import EXPECTED, seed

URL = "/admin/rapporten/dataset/f_payments.ods"


def _login_as(client, db, email: str, roles: tuple[str, ...]):
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
    bestaand = {r.role_code for r in user.roles}
    for role in roles:
        if role not in bestaand:
            db.add(UserRole(user_id=user.id, role_code=role))
    db.flush()
    client.cookies.set(SESSION_COOKIE, make_session_value(email))


def test_the_download_needs_a_session(client):
    assert client.get(URL).status_code == 401


def test_a_finance_only_user_does_not_reach_reporting(client, db_session):
    """No new security surface: FINANCE alone is not a back-office role here.

    The reason is asserted and not just the status (#680) — a 403 is also what a
    missing CSRF token or an expired session produces, and those would need a
    different fix.
    """
    seed(db_session)
    _login_as(client, db_session, "alleen-penning@example.com", ("FINANCE",))
    antwoord = client.get(URL)
    assert antwoord.status_code == 403
    assert antwoord.json()["detail"] == "Geen toegang"


def test_an_admin_and_an_operator_both_get_the_file(client, db_session):
    seed(db_session)
    _login_as(client, db_session, "bestuurslid-rapport@example.com", ("ADMIN",))
    assert client.get(URL).status_code == 200

    _login_as(client, db_session, "platformbeheer@example.com", ("OPERATOR",))
    assert client.get(URL).status_code == 200


def test_an_unknown_fact_is_refused_before_anything_is_queried(client, db_session):
    seed(db_session)
    _login_as(client, db_session, "beheer@example.com", ("ADMIN",))
    antwoord = client.get("/admin/rapporten/dataset/f_verzonnen.ods")
    assert antwoord.status_code == 422
    assert "Onbekend feit" in antwoord.json()["detail"]


def test_an_admin_gets_a_spreadsheet_with_this_tenant_s_rows(client, db_session):
    """The bytes are a real .ods, and its numbers are the seed's numbers.

    Reading the file back rather than trusting the content type: a route that
    returns an empty document with the right header would pass any check that
    stops at the status code.
    """
    from odf.opendocument import load
    from odf.table import Table, TableRow

    seed(db_session)
    _login_as(client, db_session, "beheer@example.com", ("ADMIN",))
    antwoord = client.get(URL)

    assert antwoord.status_code == 200
    assert antwoord.headers["content-type"].startswith(
        "application/vnd.oasis.opendocument.spreadsheet")
    assert "rapportering-betalingen.ods" in antwoord.headers["content-disposition"]

    document = load(BytesIO(antwoord.content))
    tabel = document.getElementsByType(Table)[0]
    rijen = tabel.getElementsByType(TableRow)
    # One header row plus one row per payment record of tenant A. Tenant B's
    # 500,00 is not in this file, and that is the whole point of the count.
    assert len(rijen) == EXPECTED["payments"]["count"] + 1


def test_the_download_and_the_report_agree_on_the_total(client, db_session):
    """One number, two ways out of the system (CR-06 §2.3)."""
    from app.domains.reporting.api import Selection, run_selection
    from tests._reporting_seed import TENANT_A

    seed(db_session)
    report = run_selection(
        db_session, Selection(object_keys=("payment_amount",)),
        tenant_id=TENANT_A)
    assert Decimal(report.rows[0]["payment_amount"]) == EXPECTED["payments"]["amount"]

    from app.domains.reporting.api import load_dataset
    dataset = load_dataset(db_session, "f_payments", tenant_id=TENANT_A)
    kolom = dataset.headers.index("amount")
    som = sum((Decimal(str(rij[kolom])) for rij in dataset.rows), Decimal("0"))
    assert som == Decimal(report.rows[0]["payment_amount"])

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


def test_geneste_refund_heeft_bewerken_editor(client, db_session):
    """#515-vervolg: een terugbetaling die genest onder haar charge staat, krijgt de
    unified 'Bewerken'-editor (effectieve uitbetaling registreren), niet enkel
    'Verwijder' — net zoals een gewone betaling."""
    from app.domains.payment.api import create_refund

    _make_finance(db_session)
    charge = _record(db_session, amount="30.00", status="paid")
    charge.amount_paid = Decimal("30.00")
    db_session.flush()
    # Nog-niet-uitbetaalde terugbetaling (pending) genest onder de charge.
    refund = create_refund(db_session, charge.id, Decimal("10.00"),
                           actor="fin@test", settled=False)
    db_session.commit()

    _login(client)
    html = client.get("/admin/betalingen/lijst").text
    # De geneste refund-regel biedt de bewerk-editor aan (post naar zijn eigen id).
    assert f"/admin/betalingen/{refund.id}/bewerken" in html


def _registratie_record(db, naam: str, amount: str, ogm: str, status="pending"):
    """Betaling met een échte naam erachter.

    `contact_name` is geen kolom op PaymentRecord: het wordt afgeleid uit de
    registratie (status_router). Op het record zetten doet dus niets — dan zoek je
    naar iets wat de lijst nooit rendert.
    """
    from tests.conftest import seed_activity_with_product
    from app.domains.activities.api import Registration

    activity, comp, _product = seed_activity_with_product(db, price=amount)
    reg = Registration(activity_id=activity.id, component_id=comp.id,
                       registration_type="INDIVIDUAL", contact_name=naam)
    db.add(reg)
    db.flush()
    rec = PaymentRecord(payable_type="registration", payable_id=reg.id,
                        amount=Decimal(amount), method="transfer", status=status,
                        structured_communication=ogm)
    db.add(rec)
    db.flush()
    return rec


def test_betalingen_zoekt_op_naam_ogm_en_omschrijving(client, db_session):
    """#591: het zoekveld dekt de drie dingen waarmee je een betaling in de hand
    terugvindt — de naam, de gestructureerde mededeling en de omschrijving."""
    _registratie_record(db_session, "An Peeters", "25.00", "+++123/4567/89012+++")
    _registratie_record(db_session, "Bram Janssens", "40.00", "+++999/8888/77777+++")
    db_session.commit()
    _login(client)

    op_naam = client.get("/admin/betalingen/lijst", params={"q": "peeters"}).text
    assert "An Peeters" in op_naam and "Bram Janssens" not in op_naam

    op_ogm = client.get("/admin/betalingen/lijst", params={"q": "999/8888"}).text
    assert "Bram Janssens" in op_ogm and "An Peeters" not in op_ogm


def test_betalingen_zoek_werkt_binnen_het_statusfilter(client, db_session):
    """De zoekterm mag geen records terugtoveren die het filter net uitsloot."""
    _registratie_record(db_session, "Cara Claes", "25.00", "+++111/1111/11111+++",
                        status="paid")
    _registratie_record(db_session, "Cara Claes", "30.00", "+++222/2222/22222+++",
                        status="pending")
    db_session.commit()
    _login(client)

    html = client.get("/admin/betalingen/lijst",
                      params={"q": "cara", "status": "paid"}).text
    assert "25.00" in html and "30.00" not in html


def test_betalingen_zoekveld_staat_op_de_pagina_niet_in_het_fragment(client, db_session):
    """De filterbalk swapt de kaartenlijst; zat het zoekveld daarin, dan verloor je
    focus bij elke aanslag (#591)."""
    _login(client)
    pagina = client.get("/admin/betalingen").text
    assert 'type="search"' in pagina and 'name="q"' in pagina
    fragment = client.get("/admin/betalingen/lijst").text
    assert 'type="search"' not in fragment

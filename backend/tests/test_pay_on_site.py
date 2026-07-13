"""Regressietests voor de product-optie 'ter plaatse te betalen (eigen budget)' (#373).

Dekt alle scenario's, telkens voor **zowel de registratie** (totaal → Mollie/
betaalrecord) **als de bevestigingsmail**:
  - alleen betalend        → totaal > 0, mail toont bedrag + Totaal
  - alleen gratis          → totaal 0, mail toont "gratis", geen Totaal
  - alleen eigen budget    → totaal 0, mail toont "ter plaatse te betalen (eigen
                             budget)" zonder bedrag, geen Totaal
  - gemengd                → totaal = enkel het betalende product; mail toont elk
                             type correct
"""
from datetime import date, timedelta
from decimal import Decimal


def _seed(db, products):
    """Activiteit + één onderdeel + de opgegeven producten. Elk product-dict:
    {name, [price], [is_free], [pay_on_site]}."""
    from app.domains.activities.api import Activity, ActivityDate
    from app.domains.activities.api import ActivitySubRegistration, ActivityProduct

    act = Activity(name="Wijnbezoek")
    db.add(act)
    db.flush()
    db.add(ActivityDate(activity_id=act.id, start_date=date.today() + timedelta(days=30)))
    db.flush()
    comp = ActivitySubRegistration(
        activity_id=act.id, name="Deelname", registration_type_code="INDIVIDUAL",
        price=Decimal("0"), is_free=True,
    )
    db.add(comp)
    db.flush()
    made = []
    for p in products:
        prod = ActivityProduct(
            component_id=comp.id, name=p["name"], price=Decimal(p.get("price", "0")),
            is_free=p.get("is_free", False), pay_on_site=p.get("pay_on_site", False),
        )
        db.add(prod)
        made.append(prod)
    db.flush()
    return act, comp, made


def _register(client, activity_id, comp_id, items, email, payment_method="ONLINE"):
    body = {
        "contact_name": "Test", "contact_email": email,
        "component_id": comp_id, "items": items,
    }
    if payment_method is not None:
        body["payment_method"] = payment_method
    return client.post(f"/api/v1/activities/{activity_id}/register", json=body)


def _payment_amount(db):
    """Het bedrag van het (enige) betaalrecord in deze geïsoleerde test, of None."""
    from app.domains.payment.api import PaymentRecord
    rec = db.query(PaymentRecord).filter(PaymentRecord.payable_type == "registration").first()
    return rec.amount if rec else None


def _mail_body(recipient):
    """Body van de laatste bevestigingsmail (via een eigen sessie: de mail wordt in
    een background-task met een aparte SessionLocal gelogd)."""
    from app.database import SessionLocal
    from app.domains.mail.models import EmailLog
    s = SessionLocal()
    try:
        row = (
            s.query(EmailLog).filter(EmailLog.recipient == recipient)
            .order_by(EmailLog.id.desc()).first()
        )
        return row.body if row else ""
    finally:
        s.close()


def test_registration_betalend(client, db_session, mock_mollie):
    act, comp, (diner,) = _seed(db_session, [{"name": "Diner", "price": "30.00"}])
    r = _register(client, act.id, comp.id, [{"product_id": diner.id, "quantity": 1}], "betalend@example.com")
    assert r.status_code == 200, r.text
    assert _payment_amount(db_session) == Decimal("30.00")
    body = _mail_body("betalend@example.com")
    assert "Diner × 1" in body and "/ stuk" in body
    assert "Totaal:" in body and "30.00" in body


def test_registration_gratis(client, db_session):
    act, comp, (drank,) = _seed(db_session, [{"name": "Welkomstdrankje", "is_free": True}])
    r = _register(client, act.id, comp.id, [{"product_id": drank.id, "quantity": 2}],
                  "gratis@example.com", payment_method=None)
    assert r.status_code == 200, r.text
    assert _payment_amount(db_session) is None  # niets te betalen
    body = _mail_body("gratis@example.com")
    assert "Welkomstdrankje × 2 — gratis" in body
    assert "Totaal:" not in body
    assert "/ stuk" not in body


def test_registration_eigen_budget(client, db_session):
    act, comp, (eten,) = _seed(db_session, [{"name": "Eten na wijnbezoek", "pay_on_site": True, "price": "15.00"}])
    r = _register(client, act.id, comp.id, [{"product_id": eten.id, "quantity": 1}],
                  "eigen@example.com", payment_method=None)
    assert r.status_code == 200, r.text
    assert _payment_amount(db_session) is None  # eigen budget → niets via het portaal
    body = _mail_body("eigen@example.com")
    assert "Eten na wijnbezoek × 1 — ter plaatse te betalen (eigen budget)" in body
    assert "15.00" not in body       # geen richtprijs tonen
    assert "Totaal:" not in body


def test_registration_gemengd(client, db_session, mock_mollie):
    act, comp, prods = _seed(db_session, [
        {"name": "Diner", "price": "30.00"},
        {"name": "Welkomstdrankje", "is_free": True},
        {"name": "Eten na wijnbezoek", "pay_on_site": True, "price": "15.00"},
    ])
    items = [{"product_id": p.id, "quantity": 1} for p in prods]
    r = _register(client, act.id, comp.id, items, "gemengd@example.com")
    assert r.status_code == 200, r.text
    # Enkel het betalende product telt mee.
    assert _payment_amount(db_session) == Decimal("30.00")
    body = _mail_body("gemengd@example.com")
    assert "Diner × 1" in body and "30.00" in body
    assert "Welkomstdrankje × 1 — gratis" in body
    assert "Eten na wijnbezoek × 1 — ter plaatse te betalen (eigen budget)" in body
    assert "Totaal:" in body

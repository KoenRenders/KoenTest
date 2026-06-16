"""OpenDocument-export per onderdeel (#85/#200): aantallen per product + financials
uit de live DB, met een totaalrij. Admin-only."""
from decimal import Decimal
from io import BytesIO

from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.teletype import extractText

from app.domains.payment_status.models import PaymentRecord
from app.models.activity import Registration, RegistrationItem
from app.models.activity_sub_registration import ActivityProduct
from tests.conftest import seed_activity_with_product

_ODS_MIME = "opendocument.spreadsheet"


def _cell_value(tc):
    value = tc.getAttribute("value")
    if value is not None:
        num = float(value)
        return int(num) if num.is_integer() else num
    return extractText(tc)


def _load(resp):
    doc = load(BytesIO(resp.content))
    table = doc.getElementsByType(Table)[0]
    rows = []
    for tr in table.getElementsByType(TableRow):
        cells = []
        for tc in tr.getElementsByType(TableCell):
            repeat = int(tc.getAttribute("numbercolumnsrepeated") or 1)
            cells.extend([_cell_value(tc)] * repeat)
        rows.append(cells)
    return rows


def test_export_requires_admin(client, db_session):
    _, comp, _ = seed_activity_with_product(db_session)
    resp = client.get(f"/api/v1/activities/{comp.activity_id}/components/{comp.id}/export")
    assert resp.status_code in (401, 403)


def test_export_unknown_component_404(client, db_session, admin_headers):
    _, comp, _ = seed_activity_with_product(db_session)
    resp = client.get(
        f"/api/v1/activities/{comp.activity_id}/components/{comp.id + 9999}/export",
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_export_quantities_and_financials(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id

    # Inschrijving: 2 stuks → verschuldigd €36.
    reg_resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 2}],
    })
    assert reg_resp.status_code in (200, 201), reg_resp.text

    charge = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.type == "charge",
    ).order_by(PaymentRecord.created_at.desc()).first()
    # Penningmeester boekt de overschrijving (€36) en betaalt €6 terug.
    client.patch(f"/api/v1/payment-status/records/{charge.id}",
                 json={"status": "paid", "amount_paid": "36.00"}, headers=admin_headers)
    client.post(f"/api/v1/payment-status/records/{charge.id}/refund",
                json={"amount": "6.00"}, headers=admin_headers)

    resp = client.get(
        f"/api/v1/activities/{activity_id}/components/{comp.id}/export",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert _ODS_MIME in resp.headers.get("content-type", "")
    assert "attachment" in resp.headers.get("content-disposition", "")

    rows = _load(resp)
    headers = list(rows[0])
    assert headers[0] == "Naam"
    assert "Verschuldigd" in headers
    assert "Terugbetaald" in headers

    i_due = headers.index("Verschuldigd")
    i_offline = headers.index("Betaald overschr./cash")
    i_refunded = headers.index("Terugbetaald")
    i_saldo = headers.index("Saldo")

    data = rows[1]
    assert data[0] == "An Janssens"
    assert data[1] == 2  # aantal van het product (eerste productkolom)
    assert data[i_due] == 36.0
    assert data[i_offline] == 36.0
    assert data[i_refunded] == 6.0
    assert data[i_saldo] == 6.0  # 36 verschuldigd - (36 betaald - 6 terug) = 6

    total = rows[-1]
    assert total[0] == "Totaal"
    assert total[1] == 2
    assert total[i_due] == 36.0
    assert total[i_refunded] == 6.0
    assert total[i_saldo] == 6.0


def test_export_aggregates_duplicate_product_lines(client, db_session, admin_headers):
    """#85: twee aparte bestelregels van hetzelfde product worden in de export per
    product opgeteld (1 + 2 = 3), niet als losse/verloren aantallen."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    reg_resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "An", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert reg_resp.status_code in (200, 201), reg_resp.text
    reg = db_session.query(Registration).filter(
        Registration.component_id == comp.id).order_by(Registration.id.desc()).first()
    # Zelfde product nog eens als aparte regel (×2).
    client.post(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items",
                json={"product_id": product.id, "quantity": 2}, headers=admin_headers)

    rows = _load(client.get(f"/api/v1/activities/{activity_id}/components/{comp.id}/export",
                            headers=admin_headers))
    col = 1  # de enige productkolom (na "Naam")
    data_rows = [r for r in rows[1:] if r[0] not in (None, "", "Totaal")]
    assert any(r[col] == 3 for r in data_rows)
    total_row = next(r for r in rows if r[0] == "Totaal")
    assert total_row[col] == 3


def test_export_empty_component_does_not_crash(client, db_session, admin_headers):
    _, comp, _ = seed_activity_with_product(db_session, price="18.00")
    resp = client.get(f"/api/v1/activities/{comp.activity_id}/components/{comp.id}/export",
                      headers=admin_headers)
    assert resp.status_code == 200, resp.text
    rows = _load(resp)
    assert rows[0][0] == "Naam"
    assert rows[-1][0] == "Totaal"  # totaalrij bestaat ook zonder inschrijvingen


def test_export_multiple_products_and_registrations(client, db_session, admin_headers):
    _, comp, p1 = seed_activity_with_product(db_session, price="10.00")
    p2 = ActivityProduct(component_id=comp.id, name="Tweede", price=Decimal("5.00"), is_free=False)
    db_session.add(p2)
    db_session.flush()
    activity_id = comp.activity_id

    # Inschrijving A: 2× p1, 1× p2 = 25 ; B: 3× p2 = 15
    client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "A", "contact_email": "a@example.com", "component_id": comp.id,
        "payment_method": "TRANSFER",
        "items": [{"product_id": p1.id, "quantity": 2}, {"product_id": p2.id, "quantity": 1}],
    })
    client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "B", "contact_email": "b@example.com", "component_id": comp.id,
        "payment_method": "TRANSFER",
        "items": [{"product_id": p2.id, "quantity": 3}],
    })

    resp = client.get(f"/api/v1/activities/{activity_id}/components/{comp.id}/export", headers=admin_headers)
    rows = _load(resp)
    headers = list(rows[0])
    i_due = headers.index("Verschuldigd")
    # Productkolommen staan op index 1 (p1) en 2 (p2).
    total = rows[-1]
    assert total[1] == 2          # totaal p1
    assert total[2] == 4          # totaal p2 (1 + 3)
    assert total[i_due] == 40.0   # 25 + 15


def test_export_online_payment_in_online_column(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "An", "contact_email": "an@example.com", "component_id": comp.id,
        "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    reg = db_session.query(Registration).filter(Registration.component_id == comp.id).first()
    # Vervang de betaling door een betaalde online-charge.
    db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.payable_id == reg.id,
    ).delete()
    db_session.add(PaymentRecord(
        payable_type="registration", payable_id=reg.id, amount=Decimal("18.00"),
        amount_paid=Decimal("18.00"), method="online", status="paid", type="charge",
    ))
    db_session.flush()

    resp = client.get(f"/api/v1/activities/{activity_id}/components/{comp.id}/export", headers=admin_headers)
    rows = _load(resp)
    headers = list(rows[0])
    i_online = headers.index("Betaald online")
    i_offline = headers.index("Betaald overschr./cash")
    assert rows[1][i_online] == 18.0
    assert rows[1][i_offline] == 0.0

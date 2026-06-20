"""ODS-export van alle betalingen & vorderingen op de admin-betalingenpagina (#307).

Eén blad met de zichtbare details + een totaalrij te betalen / betaald / saldo
(netto). Admin/penningmeester-only.
"""
from io import BytesIO

from odf.opendocument import load
from odf.table import Table, TableRow, TableCell
from odf.teletype import extractText

from app.domains.payment_status.models import PaymentRecord
from tests.conftest import seed_activity_with_product

_EXPORT = "/api/v1/payment-status/records/export"


def _cell_value(tc):
    value = tc.getAttribute("value")
    if value is not None:
        num = float(value)
        return int(num) if num.is_integer() else num
    return extractText(tc)


def _rows(resp):
    doc = load(BytesIO(resp.content))
    table = doc.getElementsByType(Table)[0]
    out = []
    for tr in table.getElementsByType(TableRow):
        cells = []
        for tc in tr.getElementsByType(TableCell):
            repeat = int(tc.getAttribute("numbercolumnsrepeated") or 1)
            cells.extend([_cell_value(tc)] * repeat)
        out.append(cells)
    return out


def test_payments_export_requires_auth(client, db_session):
    resp = client.get(_EXPORT)
    assert resp.status_code in (401, 403)


def test_payments_export_records_and_totals(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 2}],
    })
    charge = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.type == "charge",
    ).order_by(PaymentRecord.created_at.desc()).first()
    client.patch(f"/api/v1/payment-status/records/{charge.id}",
                 json={"status": "paid", "amount_paid": "36.00"}, headers=admin_headers)

    resp = client.get(_EXPORT, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert "opendocument.spreadsheet" in resp.headers.get("content-type", "")
    assert "attachment" in resp.headers.get("content-disposition", "")

    rows = _rows(resp)
    headers = list(rows[0])
    for h in ("Waarvoor", "Soort", "Te betalen", "Betaald", "Saldo"):
        assert h in headers, h
    i_due = headers.index("Te betalen")
    i_paid = headers.index("Betaald")
    i_saldo = headers.index("Saldo")
    i_what = headers.index("Waarvoor")

    data = [r for r in rows[1:-1]]
    assert any("An Janssens" in str(r[i_what]) for r in data)

    total = rows[-1]
    assert total[0] == "Totaal"
    assert total[i_due] == 36.0
    assert total[i_paid] == 36.0
    assert total[i_saldo] == 0.0


def test_payments_export_respects_context_filter(client, db_session, admin_headers):
    """De export volgt het paginafilter (#90/#308): context=membership weert de
    activiteit-inschrijving; context=comp-<id> houdt ze."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 2}],
    })

    # context=membership → de (enige) activiteit-inschrijving valt weg, totaal 0.
    resp = client.get(_EXPORT, headers=admin_headers, params={"context": "membership"})
    assert resp.status_code == 200, resp.text
    rows = _rows(resp)
    headers = list(rows[0])
    i_what = headers.index("Waarvoor")
    i_due = headers.index("Te betalen")
    assert not any("An Janssens" in str(r[i_what]) for r in rows[1:-1])
    assert rows[-1][i_due] == 0

    # context=comp-<id> → de inschrijving staat er wél in.
    resp2 = client.get(_EXPORT, headers=admin_headers, params={"context": f"comp-{comp.id}"})
    rows2 = _rows(resp2)
    assert any("An Janssens" in str(r[i_what]) for r in rows2[1:-1])
    assert rows2[-1][i_due] == 36.0

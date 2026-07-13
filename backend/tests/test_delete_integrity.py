"""Delete-integriteit: een gezin/lidmaatschap/persoon verwijderen terwijl er
betalingen (en registraties) aan hangen mag de financiële overzichten en de
ledenwijzigingen-export niet breken, en mag geen weesbetalingen achterlaten (#82-context)."""
from datetime import date

from app.domains.payment.api import PaymentRecord
from app.domains.payment.api import PaymentRecordHistory
from app.models.member import Membership
from app.domains.mdm.api import Member
from app.domains.mdm.api import ExternalNumber
from tests.conftest import seed_postal_code


def _family_payload(email="lid@example.com"):
    return {
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [{
            "last_name": "Janssens", "first_name": "An", "email": email,
            "mobile": "0470123456", "relation_type": "HOOFDLID",
        }],
    }


def _create_family(client, db_session):
    seed_postal_code(db_session)
    resp = client.post("/api/v1/families", json=_family_payload())
    assert resp.status_code == 201, resp.text
    member = db_session.query(Member).order_by(Member.id.desc()).first()
    return member


def test_delete_family_with_membership_payment(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    membership = db_session.query(Membership).filter(Membership.member_id == member.id).first()
    pay = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "membership", PaymentRecord.payable_id == membership.id,
    ).first()
    assert pay is not None  # er is een lidmaatschap-betaling

    # Gezin verwijderen mag niet falen.
    resp = client.delete(f"/api/v1/families/{member.id}", headers=admin_headers)
    assert resp.status_code == 204, resp.text

    # Het betaaloverzicht mag niet crashen op de (nu lidmaatschap-loze) betaling.
    overview = client.get("/api/v1/payment-status/records", headers=admin_headers)
    assert overview.status_code == 200, overview.text

    # De betaling is een financieel feit en BLIJFT bestaan (niet stil gewist bij
    # gezin-delete). De admin kan ze desgewenst apart verwijderen.
    leftover = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "membership", PaymentRecord.payable_id == membership.id,
    ).first()
    assert leftover is not None

    # De verwijdering van het gezin staat wél in de ledenwijzigingen-export.
    changes = client.get("/api/v1/admin/member-changes",
                         params={"since": date.today().isoformat()}, headers=admin_headers).json()
    assert any(c["operation_label"] == "Verwijderd" for c in changes)


def test_admin_can_delete_payment_record(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    membership = db_session.query(Membership).filter(Membership.member_id == member.id).first()
    pay = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "membership", PaymentRecord.payable_id == membership.id,
    ).first()
    pay_id = pay.id

    # Niet-admin mag niet.
    assert client.delete(f"/api/v1/payment-status/records/{pay_id}").status_code in (401, 403)

    # Admin verwijdert de betaling bewust.
    resp = client.delete(f"/api/v1/payment-status/records/{pay_id}", headers=admin_headers)
    assert resp.status_code == 204, resp.text
    assert db_session.query(PaymentRecord).filter(PaymentRecord.id == pay_id).first() is None

    # Het financiële feit blijft in de audit-history bewaard.
    hist = db_session.query(PaymentRecordHistory).filter(
        PaymentRecordHistory.payment_record_id == pay_id,
        PaymentRecordHistory.operation == "delete",
    ).first()
    assert hist is not None
    assert hist.action == "payment_deleted"


def test_delete_unknown_payment_record_404(client, admin_headers):
    assert client.delete("/api/v1/payment-status/records/nope", headers=admin_headers).status_code == 404


def test_delete_family_with_external_number(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    mp = member.member_persons[0]
    db_session.add(ExternalNumber(person_id=mp.person_id, source="ledenadministratie", external_id="OUD-123"))
    db_session.flush()

    resp = client.delete(f"/api/v1/families/{member.id}", headers=admin_headers)
    assert resp.status_code == 204, resp.text

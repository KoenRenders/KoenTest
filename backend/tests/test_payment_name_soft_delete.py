"""Een betaling blijft de naam tonen na soft-delete van het gezin/persoon (#190).

Soft-delete = bewaren, niet wissen: het betalingen-scherm (financiële view) verrijkt
met `include_deleted=True`, dus de naam blijft zichtbaar i.p.v. '—'."""
from app.models.member import Member, MemberPerson, Person
from app.soft_delete import soft_delete
from tests.conftest import seed_postal_code


def _family_with_membership(client, db):
    seed_postal_code(db)
    resp = client.post("/api/v1/families", json={
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [{"last_name": "Wiske", "first_name": "Suske",
                     "email": "suske@suske.be", "mobile": "0470111111",
                     "relation_type": "HOOFDLID"}],
    })
    assert resp.status_code == 201, resp.text
    return db.query(Member).order_by(Member.id.desc()).first()


def _membership_record(client, admin_headers):
    recs = client.get("/api/v1/payment-status/records", headers=admin_headers).json()
    return next(r for r in recs if r["payable_type"] == "membership")


def test_registration_description_survives_activity_soft_delete(client, db_session, admin_headers):
    """#190: na soft-delete van de activiteit blijft de betalingsrij de activiteitnaam
    tonen (de verrijking haalt de activiteit op met include_deleted)."""
    from tests.conftest import seed_activity_with_product
    from app.models.activity import Activity, Registration

    _, comp, product = seed_activity_with_product(db_session, price="12.00")
    resp = client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        "contact_name": "An", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert resp.status_code in (200, 201), resp.text
    reg = db_session.query(Registration).filter(
        Registration.component_id == comp.id).order_by(Registration.id.desc()).first()

    def _rec():
        recs = client.get("/api/v1/payment-status/records", headers=admin_headers).json()
        return next(r for r in recs
                    if r["payable_type"] == "registration" and r["payable_id"] == reg.id)

    name = _rec()["description"]
    assert name  # = de activiteitnaam
    soft_delete(db_session.query(Activity).filter(Activity.id == comp.activity_id).first())
    db_session.commit()
    assert _rec()["description"] == name  # nog steeds de activiteitnaam


def test_membership_payment_keeps_name_after_soft_delete(client, db_session, admin_headers):
    member = _family_with_membership(client, db_session)
    assert _membership_record(client, admin_headers)["contact_name"] == "Suske Wiske"

    # Soft-delete het gezin (member + band + persoon), zoals de delete-actie doet.
    for mp in db_session.query(MemberPerson).filter(MemberPerson.member_id == member.id).all():
        person = db_session.query(Person).filter(Person.id == mp.person_id).first()
        if person:
            soft_delete(person)
        soft_delete(mp)
    soft_delete(member)
    db_session.commit()

    # Nog steeds de naam, geen '—'.
    assert _membership_record(client, admin_headers)["contact_name"] == "Suske Wiske"

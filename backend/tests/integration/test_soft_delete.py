"""Soft delete op het leden-domein (#166): verwijderde rijen worden globaal uit
reads gefilterd maar blijven in de DB; partiële uniciteit laat heraanmaak toe;
de history (en dus de #82-export) toont de verwijdering nog steeds."""

from datetime import date

import pytest

from app.domains.activities import service as activities_service
from app.domains.activities.api import Activity, Registration
from app.domains.auth.api import User
from app.domains.mdm.api import Member
from app.domains.membership import household_service
from app.domains.membership.api import Membership
from app.domains.membership.schemas_member import MembershipCreate
from app.domains.payment.api import PayableType, PaymentRecord
from tests import backoffice_door, payments_door
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    register_at_the_door,
    seed_activity_with_product,
    seed_postal_code,
    seeded_admin,
    sign_up_at_the_door,
)


def _payload(email="lid@example.com"):
    return {
        "street": "Milostraat",
        "house_number": "40",
        "postal_code": "2400",
        "payment_method": "transfer",
        "members": [
            {
                "last_name": "Janssens",
                "first_name": "An",
                "email": email,
                "mobile": "0470123456",
                "date_of_birth": "1980-01-01",
                "gender_code": "M",
                "relation_type": "HOOFDLID",
            }
        ],
    }


def _create_family(client, db, email="lid@example.com"):
    seed_postal_code(db)
    resp = sign_up_at_the_door(client, json=_payload(email))
    assert resp.status_code == 201, resp.text
    return db.query(Member).order_by(Member.id.desc()).first()


def test_soft_deleted_family_hidden_but_retained(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    mid = member.id
    household_service.delete_family(db_session, mid, admin=seeded_admin(db_session))

    # Verborgen voor gewone reads (member + bijhorende rijen).
    assert db_session.query(Member).filter(Member.id == mid).first() is None
    assert db_session.query(Membership).filter(Membership.member_id == mid).first() is None

    # Maar bewaard in de DB met deleted_at (opt-out include_deleted).
    kept = (
        db_session.query(Member)
        .execution_options(include_deleted=True)
        .filter(Member.id == mid)
        .first()
    )
    assert kept is not None and kept.deleted_at is not None
    kept_ms = (
        db_session.query(Membership)
        .execution_options(include_deleted=True)
        .filter(Membership.member_id == mid)
        .first()
    )
    assert kept_ms is not None and kept_ms.deleted_at is not None


def test_family_list_excludes_soft_deleted(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    household_service.delete_family(db_session, member.id, admin=seeded_admin(db_session))
    listing = household_service.list_families(db_session, _admin=seeded_admin(db_session))
    ids = [family.id for family in listing.items]
    assert member.id not in ids


def test_reregister_same_email_after_soft_delete(client, db_session, admin_headers):
    member = _create_family(client, db_session, email="x@example.com")
    household_service.delete_family(db_session, member.id, admin=seeded_admin(db_session))
    # Opnieuw inschrijven met hetzelfde e-mail/jaar mag: de dedup ziet de
    # soft-deleted niet en de partiële uniciteit blokkeert niet.
    r2 = sign_up_at_the_door(client, json=_payload("x@example.com"))
    assert r2.status_code == 201, r2.text


def test_recreate_membership_for_same_member_year_after_soft_delete(
    client, db_session, admin_headers
):
    member = _create_family(client, db_session)
    ms = db_session.query(Membership).filter(Membership.member_id == member.id).first()
    year = ms.year
    household_service.delete_membership(db_session, ms.id, admin=seeded_admin(db_session))
    # Nieuw lidmaatschap voor hetzelfde gezin+jaar mag (partiële uniciteit).
    again = household_service.create_membership_for_family(
        db_session, member.id, MembershipCreate(year=year), admin=seeded_admin(db_session)
    )
    assert again.year == year and again.id != ms.id


def test_soft_delete_still_recorded_in_member_changes(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    household_service.delete_family(db_session, member.id, admin=seeded_admin(db_session))
    changes = backoffice_door.member_changes(client, date.today().isoformat()).json()
    assert any(c["operation_label"] == "Verwijderd" for c in changes)


# ── Stage 2/3: activiteiten, betalingen, gebruikers ──────────────────────────


def test_soft_delete_activity_hides_tree_keeps_payment(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    register_at_the_door(
        client,
        activity_id,
        json={
            "contact_name": "An",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "component_id": comp.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": 1}],
        },
    )
    reg = db_session.query(Registration).filter(Registration.activity_id == activity_id).first()
    assert reg is not None

    # #1561 (Koen, 4 October 2026): an activity with a registration is refused;
    # the registration goes first, and then the payment still stays.
    with pytest.raises(activities_service.ActiviteitFout):
        activities_service.delete_activity(db_session, activity_id, actor=SEEDED_ADMIN_EMAIL)
    from app.soft_delete import soft_delete

    soft_delete(reg)
    db_session.commit()
    assert activities_service.delete_activity(db_session, activity_id, actor=SEEDED_ADMIN_EMAIL)

    # Activiteit + inschrijving verborgen, maar bewaard.
    assert db_session.query(Activity).filter(Activity.id == activity_id).first() is None
    assert db_session.query(Registration).filter(Registration.id == reg.id).first() is None
    kept = (
        db_session.query(Activity)
        .execution_options(include_deleted=True)
        .filter(Activity.id == activity_id)
        .first()
    )
    assert kept.deleted_at is not None

    # De betaling blijft een financieel feit (NIET mee soft-deleted).
    pay = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == reg.id,
        )
        .first()
    )
    assert pay is not None and pay.deleted_at is None


def test_soft_delete_payment_hidden_but_kept(client, db_session, admin_headers):
    member = _create_family(client, db_session)
    ms = db_session.query(Membership).filter(Membership.member_id == member.id).first()
    pay = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.MEMBERSHIP,
            PaymentRecord.payable_id == ms.id,
        )
        .first()
    )
    pid = pay.id
    assert payments_door.delete(client, pid).status_code == 204
    assert db_session.query(PaymentRecord).filter(PaymentRecord.id == pid).first() is None
    kept = (
        db_session.query(PaymentRecord)
        .execution_options(include_deleted=True)
        .filter(PaymentRecord.id == pid)
        .first()
    )
    assert kept is not None and kept.deleted_at is not None


def test_soft_delete_user_and_reuse_email(client, db_session, admin_headers):
    u = User(email="temp@example.com")
    db_session.add(u)
    db_session.flush()
    uid = u.id
    assert client.delete(f"/api/v1/users/{uid}", headers=admin_headers).status_code == 204
    assert db_session.query(User).filter(User.id == uid).first() is None
    # Zelfde e-mail opnieuw mag (partiële uniciteit).
    u2 = User(email="temp@example.com")
    db_session.add(u2)
    db_session.flush()
    assert u2.id != uid

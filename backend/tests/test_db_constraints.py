"""DB-constraints als laatste vangnet (#96, #97, #98).

Deze tests bewijzen dat de database zélf ongeldige toestanden weigert, ook als
een bug de service-laag zou omzeilen. Elke schending draait in een eigen
SAVEPOINT (`begin_nested`), zodat de IntegrityError netjes teruggerold wordt en
de gedeelde sessie bruikbaar blijft.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.activity import Activity, Registration, RegistrationItem
from app.models.activity_sub_registration import ActivitySubRegistration, ActivityProduct
from tests.conftest import seed_activity_with_product


def _expect_violation(db, obj):
    """Voeg obj toe en verwacht dat de DB de flush weigert."""
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(obj)
            db.flush()


# ── #96: prijs- en aantal-checks ────────────────────────────────────────────

def test_sub_registration_price_non_negative(db_session):
    from app.models.activity import ActivityDate
    activity = Activity(name="A")
    db_session.add(activity)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=10)))
    db_session.flush()
    _expect_violation(db_session, ActivitySubRegistration(
        activity_id=activity.id, name="X", registration_type_code="INDIVIDUAL",
        price=Decimal("-1"), is_free=False,
    ))


def test_sub_registration_member_price_non_negative(db_session):
    from app.models.activity import ActivityDate
    activity = Activity(name="A")
    db_session.add(activity)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=10)))
    db_session.flush()
    _expect_violation(db_session, ActivitySubRegistration(
        activity_id=activity.id, name="X", registration_type_code="INDIVIDUAL",
        price=Decimal("5"), member_price=Decimal("-1"), is_free=False,
    ))


def test_product_member_price_non_negative(db_session):
    _activity, comp, _product = seed_activity_with_product(db_session)
    _expect_violation(db_session, ActivityProduct(
        component_id=comp.id, name="Slecht", price=Decimal("5"),
        member_price=Decimal("-0.01"), is_free=False,
    ))


def test_registration_item_quantity_positive(db_session):
    activity, comp, product = seed_activity_with_product(db_session, price="10.00")
    reg = Registration(
        activity_id=activity.id, component_id=comp.id,
        registration_type="INDIVIDUAL", contact_name="Test",
    )
    db_session.add(reg)
    db_session.flush()
    _expect_violation(db_session, RegistrationItem(
        registration_id=reg.id, product_id=product.id, quantity=0,
    ))


# ── #97: RESTRICT op registration_items.product_id ──────────────────────────

def test_product_delete_blocked_while_items_exist(db_session):
    """Een product met gekoppelde inschrijvingsitems mag niet verdwijnen:
    dat zou financiële historiek wezen (RESTRICT)."""
    activity, comp, product = seed_activity_with_product(db_session, price="10.00")
    reg = Registration(
        activity_id=activity.id, component_id=comp.id,
        registration_type="INDIVIDUAL", contact_name="Test",
    )
    db_session.add(reg)
    db_session.flush()
    db_session.add(RegistrationItem(
        registration_id=reg.id, product_id=product.id, quantity=2,
    ))
    db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.delete(product)
            db_session.flush()


# ── #97: RESTRICT op member_persons.person_id ───────────────────────────────

def test_person_delete_blocked_while_member_link_exists(db_session):
    """Een persoon met een gezinskoppeling mag niet hard verdwijnen: dat zou
    member_persons-rijen wezen (RESTRICT — DB als laatste vangnet, migr. 058).
    De app hard-delete nooit een persoon (soft-delete #166); deze test bewijst
    dat een direct ``DELETE`` op de DB toch geweigerd wordt."""
    from sqlalchemy import text
    from app.domains.mdm.api import MemberPerson
    from tests.conftest import create_test_member, create_test_person

    member = create_test_member(db_session)
    person = create_test_person(db_session)
    db_session.add(MemberPerson(
        member_id=member.id, person_id=person.id, relation_type="HOOFDLID",
    ))
    db_session.flush()

    # Raw DELETE: omzeilt ORM-cascades en raakt rechtstreeks de FK-constraint.
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text("DELETE FROM mdm.persons WHERE id = :id"), {"id": person.id})


# ── #98: optionele hardening ────────────────────────────────────────────────

def test_sub_registration_max_participants_positive(db_session):
    from app.models.activity import ActivityDate
    activity = Activity(name="A")
    db_session.add(activity)
    db_session.flush()
    db_session.add(ActivityDate(activity_id=activity.id, start_date=date.today() + timedelta(days=10)))
    db_session.flush()
    _expect_violation(db_session, ActivitySubRegistration(
        activity_id=activity.id, name="X", registration_type_code="INDIVIDUAL",
        price=Decimal("0"), is_free=True, max_participants=0,
    ))

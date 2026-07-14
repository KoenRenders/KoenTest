"""Volzet-status per onderdeel (#451): zodra de som van de inschrijvings-
hoeveelheden ``max_participants`` bereikt, markeert ``list_activities`` het
onderdeel als ``is_full`` — dan toont de homepage 'Volzet' i.p.v. een
inschrijfknop. Zonder max, of onder de max, blijft het onderdeel open.
"""
from app.domains.activities.router import list_activities
from tests.conftest import seed_activity_with_product


def _register(client, activity_id, comp, product, quantity, email):
    payload = {
        "contact_name": "An Janssens", "contact_email": email,
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": quantity}],
    }
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json=payload)
    assert resp.status_code in (200, 201), resp.text


def _component(activities, activity_id, comp_id):
    activity = next(a for a in activities if a.id == activity_id)
    return next(c for c in activity.sub_registrations if c.id == comp_id)


def test_component_marked_full_when_max_reached(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, max_participants=2)
    _register(client, comp.activity_id, comp, product, quantity=2, email="vol@example.com")

    comp_vm = _component(list_activities(scope="upcoming", db=db_session),
                         comp.activity_id, comp.id)
    assert comp_vm.is_full is True


def test_component_not_full_below_max(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, max_participants=5)
    _register(client, comp.activity_id, comp, product, quantity=2, email="half@example.com")

    comp_vm = _component(list_activities(scope="upcoming", db=db_session),
                         comp.activity_id, comp.id)
    assert comp_vm.is_full is False


def test_component_without_max_is_never_full(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, max_participants=None)
    _register(client, comp.activity_id, comp, product, quantity=9, email="open@example.com")

    comp_vm = _component(list_activities(scope="upcoming", db=db_session),
                         comp.activity_id, comp.id)
    assert comp_vm.is_full is False

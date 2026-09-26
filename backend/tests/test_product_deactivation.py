"""#1191: a product can be taken off the public form without being deleted.

**Off means gone from the public form, NOT closed** (Koen, 26 September 2026). So
there are two halves to prove, and a test that only covers the first one would let
the second break silently:

* a visitor cannot pick or post an inactive product;
* the board still can, from the back office.

`test_deactivating_keeps_a_booking_whole_where_deleting_breaks_it` is the reason
the flag exists at all. Deleting a product is a soft delete, and the screens read
the LIVING products of a component, so a delete takes the product name off the
registration and the whole column off the .ods door list. That test deactivates and
deletes the same product and asserts the difference — the delete branch is not
decoration, it is the argument.

Counter-proofs actually run, not reasoned:

* removed `check_publicly_bookable` from `activities/router.py` and let only the
  template filter → `test_a_direct_post_on_an_inactive_product_is_refused` fails on
  the 200, while the form test stays green. That is exactly the "schermtruc" the
  issue warns about;
* pointed `_form_ctx` back at `component.products` → the form test fails;
* dropped the `is_active` filter out of `publicly_bookable_products` → both fail.
"""
from __future__ import annotations

import zipfile
from decimal import Decimal
from io import BytesIO

import pytest
import sqlalchemy as sa

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

PRODUCT_NAME = "Testproduct"


def _login(client) -> str:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _public_form(client, activity, component) -> str:
    respons = client.get(
        f"/activiteiten/{activity.id}/inschrijven/{component.id}")
    assert respons.status_code == 200
    return respons.text


def _registration_body(product_id: int, quantity: int = 1) -> dict:
    """A complete public registration — name, e-mail and mobile are mandatory on
    every entrance since #733, so a body without them would be refused for the
    wrong reason and the test would prove nothing about the product."""
    return {
        "contact_name": "Tester",
        "contact_email": "tester@example.com",
        "phone": "0470123456",
        "component_id": None,
        "items": [{"product_id": product_id, "quantity": quantity}],
    }


def _seed_registration(db, activity, component, product, quantity: int):
    """One stored registration on this product — the situation a deactivation must
    leave intact. Built straight on the models on purpose: it is the fixture, not
    the subject."""
    from app.domains.activities.api import Registration, RegistrationItem

    reg = Registration(activity_id=activity.id, component_id=component.id,
                       registration_type="INDIVIDUAL", contact_name="Deelnemer",
                       contact_email="deelnemer@example.com", phone="0470000000")
    db.add(reg)
    db.flush()
    db.add(RegistrationItem(registration_id=reg.id, product_id=product.id,
                            quantity=quantity))
    db.commit()
    return reg


# ── The public side ──────────────────────────────────────────────────────────

@pytest.mark.ui_serverrendered
def test_an_inactive_product_is_absent_from_the_public_form(client, db_session):
    """Test 1 of the issue.

    The active case is asserted FIRST, and not as a courtesy: an absence only
    proves something once the probe has found the thing it looks for. Without that
    line a renamed input id would make this test pass forever.
    """
    activity, component, product = seed_activity_with_product(
        db_session, price="10.00")

    html = _public_form(client, activity, component)
    assert f'id="product-{product.id}"' in html, (
        "het aantalveld staat er niet terwijl het product actief is — de "
        "zoekopdracht van deze test klopt niet")

    product.is_active = False
    db_session.commit()

    html = _public_form(client, activity, component)
    assert f'id="product-{product.id}"' not in html, (
        "een inactief product staat nog op het publieke formulier")
    assert PRODUCT_NAME not in html, (
        "de naam van het inactieve product staat nog op het formulier")


@pytest.mark.ui_agnostisch
def test_a_direct_post_on_an_inactive_product_is_refused(client, db_session):
    """Test 2 of the issue, and the one that decides whether this is more than a
    screen trick.

    The JSON entrance never renders a template, so it cannot inherit the filtering
    of the form. Counter-proof run: with the `check_publicly_bookable` call taken
    out of `register_for_activity`, this returns 200 and stores a registration
    while the form test above stays green.

    Asserts the stored state as well as the status code. A refusal that still
    writes a row is not a refusal, and `assert status >= 400` would also pass on a
    missing mobile number — the message is checked for that reason.
    """
    from app.domains.activities.api import Registration

    activity, component, product = seed_activity_with_product(
        db_session, price="10.00")
    product.is_active = False
    db_session.commit()

    body = _registration_body(product.id, quantity=2)
    body["component_id"] = component.id
    respons = client.post(f"/api/v1/activities/{activity.id}/register", json=body)

    assert respons.status_code == 400, (
        f"een rechtstreekse POST op een inactief product gaf {respons.status_code}")
    assert "niet beschikbaar" in respons.json()["detail"], (
        f"de melding legt niet uit waarom: {respons.json()['detail']!r}")
    assert db_session.query(Registration).filter(
        Registration.activity_id == activity.id).count() == 0, (
        "de inschrijving is toch bewaard")


@pytest.mark.ui_agnostisch
def test_an_active_product_still_registers(client, db_session):
    """The other side of test 2: the refusal is aimed at the flag and not at the
    endpoint. Without this, deactivating everything would look like a pass."""
    from app.domains.activities.api import Registration

    activity, component, product = seed_activity_with_product(
        db_session, price="0.00", is_free=True)

    body = _registration_body(product.id)
    body["component_id"] = component.id
    respons = client.post(f"/api/v1/activities/{activity.id}/register", json=body)

    assert respons.status_code in (200, 201), respons.text
    assert db_session.query(Registration).filter(
        Registration.activity_id == activity.id).count() == 1


# ── The back office ──────────────────────────────────────────────────────────

@pytest.mark.ui_serverrendered
def test_the_back_office_can_still_book_an_inactive_product(client, db_session):
    """Test 3 of the issue: inactive is not closed.

    Goes through the real admin entrance and not through `add_order_line`
    directly, because what is being asserted is that the two entrances keep
    different rules — a direct call would stay green even if the public rule were
    moved into the shared service path and started refusing the board too.
    """
    from app.domains.activities.api import Registration, RegistrationItem

    activity, component, product = seed_activity_with_product(
        db_session, price="10.00")
    product.is_active = False
    db_session.commit()
    reg = Registration(activity_id=activity.id, component_id=component.id,
                       registration_type="INDIVIDUAL", contact_name="Gastenlijst",
                       contact_email="bestuur@example.com", phone="0470000000")
    db_session.add(reg)
    db_session.commit()

    csrf = _login(client)
    respons = client.post(f"/admin/inschrijvingen/{reg.id}/regels",
                          data={"product_id": str(product.id), "quantity": "8"},
                          headers={"X-CSRF-Token": csrf})

    assert respons.status_code == 200, respons.text
    regels = db_session.query(RegistrationItem).filter(
        RegistrationItem.registration_id == reg.id).all()
    assert [r.quantity for r in regels] == [8], (
        "het bestuur kon geen regel op een inactief product zetten")


# ── Why the flag exists instead of a delete ──────────────────────────────────

@pytest.mark.ui_serverrendered
def test_deactivating_keeps_a_booking_whole_where_deleting_breaks_it(
        client, db_session):
    """Test 4 of the issue, with its counter-proof inside the test.

    Three things must survive a deactivation: the product name on the
    registration detail, the column plus its quantities in the .ods door list,
    and the amount due. The same three are then measured after a DELETE of the
    same product, where all three fall over — that contrast is the argument for
    the flag, so it belongs in the suite and not only in an analysis.

    **`expunge_all()` and not `expire_all()` after the delete, and that is the
    whole reason this test is trustworthy.** A soft-deleted product stays
    reachable through `item.product` as long as it sits in the session's identity
    map: a many-to-one load by primary key is answered from that map without a
    SELECT, so the global soft-delete filter never runs. Measured: with
    `expire_all()` the amount due still reads 80,00 after the delete, and the
    counter-proof silently proved nothing. Every HTTP request gets a fresh
    session, so an empty identity map is what production actually does — and in
    this suite the client shares the test's session, so it has to be emptied by
    hand. The collection load (`component.products`) is filtered either way,
    which is why the name and the column disappear without this.

    The .ods is a zip; its `content.xml` carries the header row and the cell
    values, which is where both the column and the quantity are visible.
    """
    from app.domains.activities.api import (Activity, ActivityProduct,
                                            ActivitySubRegistration,
                                            build_component_export_ods)
    from app.soft_delete import soft_delete

    activity, component, product = seed_activity_with_product(
        db_session, price="10.00")
    reg = _seed_registration(db_session, activity, component, product, quantity=8)
    activity_id, component_id, product_id, reg_id = (
        activity.id, component.id, product.id, reg.id)

    def _detail_html() -> str:
        respons = client.get(f"/admin/inschrijvingen/{reg_id}")
        assert respons.status_code == 200
        return respons.text

    def _doorlist() -> str:
        ods = build_component_export_ods(
            db_session,
            db_session.get(Activity, activity_id),
            db_session.get(ActivitySubRegistration, component_id))
        with zipfile.ZipFile(BytesIO(ods)) as zf:
            return zf.read("content.xml").decode()

    _login(client)

    # ── deactivated: everything stays ──
    db_session.get(ActivityProduct, product_id).is_active = False
    db_session.commit()

    detail = _detail_html()
    assert PRODUCT_NAME in detail, (
        "het inschrijvingsdetail toont de productnaam niet meer")

    lijst = _doorlist()
    assert PRODUCT_NAME in lijst, "de deurlijst verloor haar kolom"
    assert 'office:value="8"' in lijst, "de deurlijst verloor het aantal"
    assert "80.0" in lijst, "het verschuldigde bedrag staat niet in de deurlijst"

    # ── deleted: the same three fall over. This is the counter-proof. ──
    soft_delete(db_session.get(ActivityProduct, product_id))
    db_session.commit()
    db_session.expunge_all()

    detail = _detail_html()
    assert PRODUCT_NAME not in detail, (
        "een VERWIJDERD product zou zijn naam uit het detail moeten verliezen — "
        "klopt die aanname niet meer, dan bewijst deze test niets over de vlag")

    lijst = _doorlist()
    assert PRODUCT_NAME not in lijst, "de kolom overleefde het verwijderen"
    assert 'office:value="8"' not in lijst, "het aantal overleefde het verwijderen"
    assert "80.0" not in lijst, "het bedrag overleefde het verwijderen"


# ── Defaults ─────────────────────────────────────────────────────────────────

@pytest.mark.ui_agnostisch
def test_a_new_product_is_active_and_an_existing_row_comes_along(db_session):
    """Test 5 of the issue, in its two halves.

    The second half writes a row **without** the column, through raw SQL, because
    that is the only way to reach the `server_default` from the migration. An
    insert through the ORM would fill the Python default in and prove nothing
    about the rows that already existed on PROD when the column arrived.
    """
    _activity, component, product = seed_activity_with_product(
        db_session, price="10.00")
    assert product.is_active is True, "een nieuw product staat niet op actief"

    rij = db_session.execute(sa.text(
        "INSERT INTO activities.activity_products "
        "(component_id, name, price, is_free, sort_order, tenant_id) "
        "VALUES (:c, :n, :p, false, 0, :t) RETURNING is_active"),
        {"c": component.id, "n": "Zonder vlag", "p": Decimal("5.00"),
         "t": component.tenant_id}).scalar()
    assert rij is True, (
        "een rij die de kolom niet meegeeft komt niet op actief terug — de "
        "server_default uit de migratie ontbreekt")

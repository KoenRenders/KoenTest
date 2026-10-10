"""The catalogue's rules (CR-21, phase 1): the life cycle, the sku, the attachment.

- `Product.check()` — the life cycle never walks back to Concept (Q74): allowed
  Concept → On sale, On sale → Discontinued, Discontinued → On sale, Concept →
  Discontinued; never back to Concept. On every flush through the listener;
- the sku is unique per tenant, at rest (`uq_product_variants_sku`);
- an attachment points at a media asset (a soft reference, no foreign key).

Broken on purpose to check these tests can go red (run, then restored), each
additively, with what failed: `return` as the first line of `Product.check()` →
the walk-back test alone (the walk back is accepted); removing the
`history.deleted` guard → the explicit-CONCEPT test alone (a new article named
Concept is refused); dropping `uq_product_variants_sku` from the migration → the
sku test alone. The walk-back rule holds on an expired instance too
(`active_history` on the column).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.product.api import (
    Product,
    ProductAttachment,
    ProductError,
    ProductStatus,
    ProductVariant,
    is_on_sale,
    list_products,
    pre_order_window,
    variants_of,
)

pytestmark = pytest.mark.ui_agnostisch


def _product(db, name: str = "T-shirt Raak", **values) -> Product:
    product = Product(name=name, **values)
    db.add(product)
    db.flush()
    return product


def test_the_allowed_life_cycle_transitions_pass(db_session):
    product = _product(db_session)
    assert product.status is ProductStatus.CONCEPT

    product.status = ProductStatus.ON_SALE
    db_session.flush()
    assert product.status is ProductStatus.ON_SALE

    product.status = ProductStatus.DISCONTINUED
    db_session.flush()
    assert product.status is ProductStatus.DISCONTINUED

    product.status = ProductStatus.ON_SALE
    db_session.flush()
    assert product.status is ProductStatus.ON_SALE


def test_concept_can_go_straight_to_discontinued(db_session):
    product = _product(db_session)
    product.status = ProductStatus.DISCONTINUED
    db_session.flush()
    assert product.status is ProductStatus.DISCONTINUED


def test_a_new_article_may_start_at_concept_explicitly(db_session):
    product = _product(db_session, status=ProductStatus.CONCEPT)
    db_session.flush()
    assert product.status is ProductStatus.CONCEPT


def test_walking_back_to_concept_is_refused(db_session):
    product = _product(db_session)
    product.status = ProductStatus.ON_SALE
    db_session.flush()

    product.status = ProductStatus.CONCEPT
    with pytest.raises(ProductError):
        db_session.flush()


def test_walking_back_to_concept_is_refused_even_when_not_loaded(db_session):
    """The rule holds on an instance that was expired before the change: the
    session expires every instance at a commit, so this is the common state."""
    product = _product(db_session)
    product.status = ProductStatus.ON_SALE
    db_session.flush()
    db_session.expire(product)

    product.status = ProductStatus.CONCEPT
    with pytest.raises(ProductError):
        db_session.flush()


def test_the_sku_is_unique_within_a_tenant(db_session):
    product = _product(db_session)
    db_session.add(
        ProductVariant(
            product_id=product.id, sku="TSH-M", properties=[{"name": "Maat", "value": "M"}]
        )
    )
    db_session.flush()

    db_session.add(
        ProductVariant(
            product_id=product.id, sku="TSH-M", properties=[{"name": "Maat", "value": "L"}]
        )
    )
    with pytest.raises(IntegrityError, match="uq_product_variants_sku"):
        db_session.flush()


def test_the_same_sku_may_stand_in_two_tenants(db_session):
    first = _product(db_session, tenant_id=2)
    second = _product(db_session, name="T-shirt", tenant_id=3)
    db_session.add(ProductVariant(product_id=first.id, tenant_id=2, sku="TSH-M", properties=[]))
    db_session.add(ProductVariant(product_id=second.id, tenant_id=3, sku="TSH-M", properties=[]))
    db_session.flush()


def test_an_attachment_points_at_a_media_asset(db_session):
    product = _product(db_session)
    db_session.add(
        ProductAttachment(product_id=product.id, media_asset_id=12345, title="Maattabel")
    )
    db_session.flush()

    assert len(product.attachments) == 1
    assert product.attachments[0].media_asset_id == 12345
    assert product.attachments[0].title == "Maattabel"


def test_variants_of_returns_the_variants_in_their_sort_order(db_session):
    product = _product(db_session)
    db_session.add_all(
        [
            ProductVariant(
                product_id=product.id, properties=[{"name": "Maat", "value": "L"}], sort_order=2
            ),
            ProductVariant(
                product_id=product.id, properties=[{"name": "Maat", "value": "S"}], sort_order=0
            ),
            ProductVariant(
                product_id=product.id, properties=[{"name": "Maat", "value": "M"}], sort_order=1
            ),
        ]
    )
    db_session.flush()

    sizes = [v.properties[0]["value"] for v in variants_of(db_session, product.id)]
    assert sizes == ["S", "M", "L"]


def test_list_products_active_only_keeps_the_ones_on_sale(db_session):
    _product(db_session, name="T-shirt")  # Concept
    on_sale = _product(db_session, name="Sweater", status=ProductStatus.ON_SALE)
    _product(db_session, name="Polo", status=ProductStatus.DISCONTINUED)

    active = list_products(db_session, active_only=True)
    assert [p.id for p in active] == [on_sale.id]
    assert len(list_products(db_session)) == 3


def test_is_on_sale_is_only_true_for_on_sale(db_session):
    product = _product(db_session)
    assert is_on_sale(db_session, product.id) is False

    product.status = ProductStatus.ON_SALE
    db_session.flush()
    assert is_on_sale(db_session, product.id) is True


def test_the_pre_order_window_opens_until_its_end_date_inclusive(db_session):
    product = _product(db_session, pre_order=True, pre_order_until=date(2026, 10, 31))

    open_, until = pre_order_window(product, date(2026, 10, 31))
    assert open_ is True and until == date(2026, 10, 31)
    open_, _ = pre_order_window(product, date(2026, 11, 1))
    assert open_ is False


def test_the_pre_order_window_stays_open_without_an_end_date(db_session):
    product = _product(db_session, pre_order=True, pre_order_until=None)
    assert pre_order_window(product, date(2099, 1, 1))[0] is True


def test_the_pre_order_window_is_closed_when_not_pre_order(db_session):
    product = _product(db_session, pre_order=False)
    assert pre_order_window(product, date(2026, 10, 31))[0] is False

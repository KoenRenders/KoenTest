"""The catalogue's rules (CR-21, phase 1): the life cycle, the sku, the attachment.

- `Product.check()` — the life cycle never walks back to Concept (Q74): allowed
  Concept → On sale, On sale → Discontinued, Discontinued → On sale, Concept →
  Discontinued; never back to Concept. On every flush through the listener;
- the sku is unique per tenant, at rest (`uq_product_variants_sku`);
- an attachment points at a media asset (a soft reference, no foreign key).

Broken on purpose to check these tests can go red (run, then restored): removing
the `history.deleted` guard from `Product.check()` → the walk-back test goes red
while the allowed transitions stay green; dropping `uq_product_variants_sku` from
the model → the sku test goes red.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.product.api import (
    Product,
    ProductAttachment,
    ProductError,
    ProductStatus,
    ProductVariant,
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


def test_walking_back_to_concept_is_refused(db_session):
    product = _product(db_session)
    product.status = ProductStatus.ON_SALE
    db_session.flush()

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

"""Deletion of a product or a size (CR-21, Q75, T19).

A product — or one of its sizes — without stock movements can be deleted, and
its prices go with it in the same transaction, through the `ProductDeleted`
event. A product with a movement cannot be deleted; it is set DISCONTINUED. The
files of a deleted article's attachments are removed through media's
`RemoveAsset` port, but only when no other attachment points at them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.media.api import MediaAsset
from app.domains.pricing.api import Price, PriceType
from app.domains.product.api import (
    Product,
    ProductAttachment,
    ProductError,
    ProductVariant,
    delete_product,
    delete_variant,
)
from app.domains.stock.api import receive

pytestmark = pytest.mark.ui_agnostisch


def _product_with_variants(db, *sizes: str) -> tuple[Product, list[ProductVariant]]:
    product = Product(name="T-shirt Raak")
    db.add(product)
    db.flush()
    variants = []
    for size in sizes:
        variant = ProductVariant(
            product_id=product.id, properties=[{"name": "Maat", "value": size}]
        )
        db.add(variant)
        variants.append(variant)
    db.flush()
    return product, variants


def test_deleting_a_product_takes_its_prices_with_it(db_session):
    product, variants = _product_with_variants(db_session, "M", "L")
    db_session.add_all(
        [
            Price(
                product_id=product.id,
                variant_id=None,
                price_type=PriceType.REGULAR,
                amount=Decimal("15.00"),
                valid_from=date(2026, 9, 1),
            ),
            Price(
                product_id=product.id,
                variant_id=variants[0].id,
                price_type=PriceType.REGULAR,
                amount=Decimal("16.00"),
                valid_from=date(2026, 9, 1),
            ),
        ]
    )
    db_session.flush()

    delete_product(db_session, product.id)
    db_session.flush()

    assert db_session.query(Price).filter(Price.product_id == product.id).count() == 0
    assert db_session.get(Product, product.id) is None


def test_a_product_with_a_movement_cannot_be_deleted(db_session):
    product, variants = _product_with_variants(db_session, "M")
    receive(db_session, variant_id=variants[0].id, quantity=10)

    with pytest.raises(ProductError):
        delete_product(db_session, product.id)


def test_deleting_a_size_keeps_the_products_own_price(db_session):
    product, variants = _product_with_variants(db_session, "M", "L")
    db_session.add_all(
        [
            Price(
                product_id=product.id,
                variant_id=None,
                price_type=PriceType.REGULAR,
                amount=Decimal("15.00"),
                valid_from=date(2026, 9, 1),
            ),
            Price(
                product_id=product.id,
                variant_id=variants[0].id,
                price_type=PriceType.REGULAR,
                amount=Decimal("16.00"),
                valid_from=date(2026, 9, 1),
            ),
        ]
    )
    db_session.flush()

    delete_variant(db_session, variants[0].id)
    db_session.flush()

    assert db_session.query(Price).filter(Price.variant_id == variants[0].id).count() == 0
    assert db_session.query(Price).filter(Price.variant_id.is_(None)).count() == 1
    assert db_session.get(Product, product.id) is not None


def test_deleting_a_product_removes_its_unshared_file(db_session):
    asset = MediaAsset(kind="sponsor", data=b"x", content_type="image/png")
    db_session.add(asset)
    db_session.flush()
    product, _ = _product_with_variants(db_session, "M")
    db_session.add(ProductAttachment(product_id=product.id, media_asset_id=asset.id))
    db_session.flush()

    delete_product(db_session, product.id)
    db_session.flush()

    assert db_session.get(MediaAsset, asset.id) is None


def test_a_shared_file_stays_while_another_attachment_points_at_it(db_session):
    asset = MediaAsset(kind="sponsor", data=b"x", content_type="image/png")
    db_session.add(asset)
    db_session.flush()
    first, _ = _product_with_variants(db_session, "M")
    second, _ = _product_with_variants(db_session, "M")
    db_session.add(ProductAttachment(product_id=first.id, media_asset_id=asset.id))
    db_session.add(ProductAttachment(product_id=second.id, media_asset_id=asset.id))
    db_session.flush()

    delete_product(db_session, first.id)
    db_session.flush()
    assert db_session.get(MediaAsset, asset.id) is not None

    delete_product(db_session, second.id)
    db_session.flush()
    assert db_session.get(MediaAsset, asset.id) is None

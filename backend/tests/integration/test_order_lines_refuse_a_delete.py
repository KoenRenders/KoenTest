"""The order-line gate of a delete (CR-21, T19): an article that stands in an
order is decommissioned, never deleted.

The gate lives in `sales`'s handler on `ProductDeleted`, as the movement gate
lives in `stock`'s — a size with an order line is refused with `SizeDeleteRefused`
(names the size at its row), a whole article with `ProductHasOrderLines`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domains.product.api import (
    Product,
    ProductVariant,
    SizeNameRefusal,
    delete_product,
    size_of,
    sync_variants,
    variants_of,
)
from app.domains.sales.api import ProductHasOrderLines, SalesOrder, SalesOrderLine

pytestmark = pytest.mark.ui_agnostisch


def _product_with_variants(db, *sizes):
    product = Product(name="T-shirt Raak")
    db.add(product)
    db.flush()
    variants = []
    for size in sizes:
        variant = ProductVariant(
            product_id=product.id,
            properties=[{"name": "Maat", "value": size}],
            sort_order=len(variants),
        )
        db.add(variant)
        db.flush()
        variants.append(variant)
    return product, variants


def _order_line_for(db, variant_id):
    order = SalesOrder()
    db.add(order)
    db.flush()
    line = SalesOrderLine(
        order_id=order.id, variant_id=variant_id, quantity=1, unit_price=Decimal("15.00")
    )
    db.add(line)
    db.flush()
    return order, line


def test_a_size_with_an_order_line_is_refused(db_session):
    """Removing a size that stands in an order is refused, and the save rolls
    back — the size stays. The refusal is sales' own (the reason says
    "bestelling"), not the movement gate's."""
    product, variants = _product_with_variants(db_session, "M", "S")
    _order_line_for(db_session, variants[0].id)

    savepoint = db_session.begin_nested()
    with pytest.raises(SizeNameRefusal) as refusal:
        sync_variants(db_session, product.id, [(str(variants[1].id), "Small")])
    savepoint.rollback()

    assert "bestelling" in str(refusal.value)

    db_session.expire_all()
    names = {variant.id: size_of(variant) for variant in variants_of(db_session, product.id)}
    assert names == {variants[0].id: "M", variants[1].id: "S"}


def test_a_product_with_an_order_line_cannot_be_deleted(db_session):
    product, variants = _product_with_variants(db_session, "M")
    _order_line_for(db_session, variants[0].id)

    with pytest.raises(ProductHasOrderLines) as refusal:
        delete_product(db_session, product.id)
    assert "bestelling" in str(refusal.value)

    db_session.expire_all()
    assert db_session.get(Product, product.id) is not None, "the article stays"

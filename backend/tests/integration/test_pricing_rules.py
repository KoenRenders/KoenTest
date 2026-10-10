"""The price question (CR-21, F3): the price of a variant on a day (T4).

`price_for` proves the flag, not the membership: `member` is a bool the caller
hands over. Who holds a valid membership is `membership`'s to say
(`has_valid_membership`) and is asked by `sales` in phase 2 (C5) — the two are
wired together there, not here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.pricing.api import Price, PriceType, price_for
from app.domains.product.api import Product, ProductVariant

pytestmark = pytest.mark.ui_agnostisch


def _variant(db) -> ProductVariant:
    product = Product(name="T-shirt Raak")
    db.add(product)
    db.flush()
    variant = ProductVariant(product_id=product.id, properties=[{"name": "Maat", "value": "M"}])
    db.add(variant)
    db.flush()
    return variant


def test_the_price_in_force_is_the_newest_start_on_or_before_the_day(db_session):
    variant = _variant(db_session)
    db_session.add_all(
        [
            Price(
                product_id=variant.product_id,
                variant_id=variant.id,
                price_type=PriceType.REGULAR,
                amount=Decimal("15.00"),
                valid_from=date(2026, 9, 1),
            ),
            Price(
                product_id=variant.product_id,
                variant_id=variant.id,
                price_type=PriceType.REGULAR,
                amount=Decimal("17.00"),
                valid_from=date(2026, 11, 1),
            ),
        ]
    )
    db_session.flush()

    assert price_for(db_session, variant.id, date(2026, 10, 1)) == Decimal("15.00")
    assert price_for(db_session, variant.id, date(2026, 12, 1)) == Decimal("17.00")
    assert price_for(db_session, variant.id, date(2026, 8, 1)) is None


def test_the_variants_price_overrides_the_products(db_session):
    variant = _variant(db_session)
    db_session.add_all(
        [
            Price(
                product_id=variant.product_id,
                variant_id=None,
                price_type=PriceType.REGULAR,
                amount=Decimal("15.00"),
                valid_from=date(2026, 9, 1),
            ),
            Price(
                product_id=variant.product_id,
                variant_id=variant.id,
                price_type=PriceType.REGULAR,
                amount=Decimal("16.00"),
                valid_from=date(2026, 9, 1),
            ),
        ]
    )
    db_session.flush()

    assert price_for(db_session, variant.id, date(2026, 10, 1)) == Decimal("16.00")


def test_a_member_pays_the_member_price_and_anyone_else_the_regular(db_session):
    variant = _variant(db_session)
    db_session.add_all(
        [
            Price(
                product_id=variant.product_id,
                variant_id=variant.id,
                price_type=PriceType.REGULAR,
                amount=Decimal("15.00"),
                valid_from=date(2026, 9, 1),
            ),
            Price(
                product_id=variant.product_id,
                variant_id=variant.id,
                price_type=PriceType.MEMBER,
                amount=Decimal("12.00"),
                valid_from=date(2026, 9, 1),
            ),
        ]
    )
    db_session.flush()

    assert price_for(db_session, variant.id, date(2026, 10, 1), member=True) == Decimal("12.00")
    assert price_for(db_session, variant.id, date(2026, 10, 1), member=False) == Decimal("15.00")


def test_a_member_without_a_member_price_pays_the_regular(db_session):
    variant = _variant(db_session)
    db_session.add(
        Price(
            product_id=variant.product_id,
            variant_id=variant.id,
            price_type=PriceType.REGULAR,
            amount=Decimal("15.00"),
            valid_from=date(2026, 9, 1),
        )
    )
    db_session.flush()

    assert price_for(db_session, variant.id, date(2026, 10, 1), member=True) == Decimal("15.00")


def test_a_variant_without_a_price_has_no_price(db_session):
    variant = _variant(db_session)
    assert price_for(db_session, variant.id, date(2026, 10, 1)) is None

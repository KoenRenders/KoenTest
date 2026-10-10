"""A price's validity cannot overlap (CR-21, C4.2).

The key `UNIQUE NULLS NOT DISTINCT (tenant_id, product_id, variant_id,
price_type, valid_from)` makes overlap impossible at rest: two prices of one
type and date are refused for a variant, and for the product too — a plain
UNIQUE would let two product-level prices in, because two NULL variants count as
different.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.pricing.api import Price, PriceType

pytestmark = pytest.mark.ui_agnostisch


def _price(db, **values) -> Price:
    price = Price(**values)
    db.add(price)
    db.flush()
    return price


def test_two_prices_of_one_variant_type_and_date_are_refused(db_session):
    _price(
        db_session,
        product_id=1,
        variant_id=10,
        price_type=PriceType.REGULAR,
        amount=Decimal("15.00"),
        valid_from=date(2026, 1, 1),
    )
    with pytest.raises(IntegrityError, match="uq_prices_validity"):
        _price(
            db_session,
            product_id=1,
            variant_id=10,
            price_type=PriceType.REGULAR,
            amount=Decimal("16.00"),
            valid_from=date(2026, 1, 1),
        )


def test_two_product_prices_of_one_type_and_date_are_refused(db_session):
    _price(
        db_session,
        product_id=1,
        variant_id=None,
        price_type=PriceType.REGULAR,
        amount=Decimal("15.00"),
        valid_from=date(2026, 1, 1),
    )
    with pytest.raises(IntegrityError, match="uq_prices_validity"):
        _price(
            db_session,
            product_id=1,
            variant_id=None,
            price_type=PriceType.REGULAR,
            amount=Decimal("16.00"),
            valid_from=date(2026, 1, 1),
        )


def test_prices_of_one_variant_are_fine_on_different_dates(db_session):
    _price(
        db_session,
        product_id=1,
        variant_id=10,
        price_type=PriceType.REGULAR,
        amount=Decimal("15.00"),
        valid_from=date(2026, 9, 1),
    )
    _price(
        db_session,
        product_id=1,
        variant_id=10,
        price_type=PriceType.REGULAR,
        amount=Decimal("17.00"),
        valid_from=date(2026, 11, 1),
    )
    db_session.flush()


def test_a_regular_and_a_member_price_may_share_a_date(db_session):
    _price(
        db_session,
        product_id=1,
        variant_id=10,
        price_type=PriceType.REGULAR,
        amount=Decimal("15.00"),
        valid_from=date(2026, 1, 1),
    )
    _price(
        db_session,
        product_id=1,
        variant_id=10,
        price_type=PriceType.MEMBER,
        amount=Decimal("12.00"),
        valid_from=date(2026, 1, 1),
    )
    db_session.flush()

"""The price question (CR-21), behind `api.py`: the price of a variant on a day."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.pricing.models import Price, PriceType
from app.domains.product.api import get_variant


def price_for(db: Session, variant_id: int, on: date, member: bool = False) -> Decimal | None:
    """The price of a variant on `on`, for a member or not (F3).

    A member with a valid membership pays the MEMBER price of the variant, else
    of the product; anyone else — or when there is no member price — pays the
    REGULAR price of the variant, else of the product. A price is in force from
    its start date until the next one of the same type starts; the latest start
    on or before `on` is the one that applies. None when the variant does not
    exist or has no price.
    """
    variant = get_variant(db, variant_id)
    if variant is None:
        return None
    product_id = variant.product_id
    if member:
        price = _latest(db, product_id, variant_id, PriceType.MEMBER, on) or _latest(
            db, product_id, None, PriceType.MEMBER, on
        )
        if price is not None:
            return price.amount
    price = _latest(db, product_id, variant_id, PriceType.REGULAR, on) or _latest(
        db, product_id, None, PriceType.REGULAR, on
    )
    return price.amount if price is not None else None


def _latest(db: Session, product_id: int, variant_id: int | None, price_type: PriceType, on: date):
    """The newest price of `price_type` for this product and variant that starts
    on or before `on` — the variant's when `variant_id` is given, the product's
    when it is None."""
    return (
        db.query(Price)
        .filter(
            Price.product_id == product_id,
            Price.variant_id == variant_id,
            Price.price_type == price_type,
            Price.valid_from <= on,
        )
        .order_by(Price.valid_from.desc())
        .first()
    )

"""The price question (CR-21), behind `api.py`: the price of a variant on a day,
and the prices a screen manages."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.pricing.models import Price, PriceType
from app.domains.product.api import get_variant


def prices_of(db: Session, product_id: int) -> list[Price]:
    """The prices of an article, newest start first (C4.2: a price ends where
    the next one of the same type starts)."""
    return (
        db.query(Price)
        .filter(Price.product_id == product_id)
        .order_by(Price.valid_from.desc(), Price.variant_id, Price.price_type)
        .all()
    )


def add_prices(
    db: Session,
    *,
    product_id: int,
    variant_id: int | None,
    valid_from: date | None,
    amount: Decimal | None,
    member_amount: Decimal | None,
) -> list[Price]:
    """Set the price from `valid_from` (C4.2): a REGULAR price always, and a
    MEMBER price when `member_amount` is given — empty means members pay the
    regular price. A variant's price overrides the product's (Q4)."""
    from app.domains.pricing.models import PriceError
    from app.i18n import _

    if valid_from is None:
        raise PriceError(_("Vul een datum in."))
    if amount is None or amount < 0:
        raise PriceError(_("Geef een prijs van nul of meer."))
    if member_amount is not None and member_amount < 0:
        raise PriceError(_("Geef een ledenprijs van nul of meer."))
    if variant_id is not None:
        variant = get_variant(db, variant_id)
        if variant is None or variant.product_id != product_id:
            raise PriceError(_("Deze maat hoort niet bij dit artikel."))
    # C4.2: a price ends where the next one of the same type starts — a second
    # price of the same type and date is refused, in words, before the key does.
    kinds = (PriceType.REGULAR,) if member_amount is None else (PriceType.REGULAR, PriceType.MEMBER)
    for price_type in kinds:
        if (
            db.query(Price)
            .filter(
                Price.product_id == product_id,
                Price.variant_id == variant_id,
                Price.price_type == price_type,
                Price.valid_from == valid_from,
            )
            .first()
            is not None
        ):
            raise PriceError(_("Er staat al een prijs voor deze maat op deze datum."))
    regular = Price(
        product_id=product_id,
        variant_id=variant_id,
        price_type=PriceType.REGULAR,
        amount=amount,
        valid_from=valid_from,
    )
    db.add(regular)
    added = [regular]
    if member_amount is not None:
        member = Price(
            product_id=product_id,
            variant_id=variant_id,
            price_type=PriceType.MEMBER,
            amount=member_amount,
            valid_from=valid_from,
        )
        db.add(member)
        added.append(member)
    db.flush()
    db.commit()
    return added


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
        price = price_in_force(db, product_id, variant_id, PriceType.MEMBER, on) or price_in_force(
            db, product_id, None, PriceType.MEMBER, on
        )
        if price is not None:
            return price.amount
    price = price_in_force(db, product_id, variant_id, PriceType.REGULAR, on) or price_in_force(
        db, product_id, None, PriceType.REGULAR, on
    )
    return price.amount if price is not None else None


def price_in_force(
    db: Session, product_id: int, variant_id: int | None, price_type: PriceType, on: date
):
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

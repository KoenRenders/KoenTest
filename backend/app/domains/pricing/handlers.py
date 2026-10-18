"""What the pricing component does when the catalogue says something is gone."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domains.pricing.models import Price
from app.kernel.contracts.product import ProductDeleted
from app.kernel.events import subscribe


@subscribe(ProductDeleted)
def drop_prices_of_deleted_product(event: ProductDeleted, db: Session) -> None:
    """The prices of a deleted product — or of one deleted size — go with it (Q75).

    Runs in the delete's transaction, so a refusal here rolls the delete back.
    A full delete also takes the product's own price (`variant_id` NULL); a
    single size's delete leaves the product and its price in place.
    """
    conditions = [Price.variant_id.in_(event.variant_ids)]
    if event.product_gone:
        conditions.append(Price.variant_id.is_(None))
    db.query(Price).filter(
        Price.product_id == event.product_id,
        or_(*conditions),
    ).delete(synchronize_session=False)

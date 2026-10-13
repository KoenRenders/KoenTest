"""The offer (CR-21): what the shop offers today, and at which price for whom.

One rule in one place (H1, H2 of the read): an article is on offer when it is in
sale and at least one of its sizes has a price valid today. A member pays the
size's member price, anyone else its regular price — `price_for` decides that
(F3). The list and the article page both ask here, and the basket and the order
of the commits that follow will too, so the rule cannot come to differ.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domains.pricing.api import price_for
from app.domains.product.api import Product, ProductStatus, list_products, size_of, variants_of
from app.kernel.clock import belgian_today


def _offered_sizes(db: Session, product: Product, *, member: bool) -> list[dict[str, Any]]:
    """The sizes of `product` that carry a price valid today, each with its name
    and the price the viewer pays (F16: "a valid price today")."""
    today = belgian_today()
    sizes: list[dict[str, Any]] = []
    for variant in variants_of(db, product.id):
        price = price_for(db, variant.id, today, member)
        if price is not None:
            sizes.append({"name": size_of(variant), "price": price})
    return sizes


def offered_products(db: Session, *, member: bool = False) -> list[dict[str, Any]]:
    """The articles the shop offers today (F16, R40): in sale, with at least one
    size whose price is valid today. Each carries its offered sizes and the lowest
    of their prices."""
    offered: list[dict[str, Any]] = []
    for product in list_products(db, active_only=True):
        sizes = _offered_sizes(db, product, member=member)
        if not sizes:
            continue
        offered.append(
            {
                "id": product.id,
                "name": product.name,
                "sizes": [size["name"] for size in sizes],
                "price": min(size["price"] for size in sizes),
            }
        )
    return offered


def article_offer(db: Session, product_id: int, *, member: bool = False) -> dict[str, Any] | None:
    """One article's offer today — its name, description and the sizes with their
    prices — or None when it is not offered: not in sale, no size with a price
    valid today, of another tenant, or deleted.

    The product is read through a filtered query, not `db.get`: a visitor types
    the id, and a primary-key load must not skip the tenant and soft-delete
    filters (H4)."""
    product = db.query(Product).filter(Product.id == product_id).one_or_none()
    if product is None or product.status is not ProductStatus.ON_SALE:
        return None
    sizes = _offered_sizes(db, product, member=member)
    if not sizes:
        return None
    return {"name": product.name, "description": product.description or "", "sizes": sizes}

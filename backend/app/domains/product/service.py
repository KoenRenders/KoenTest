"""The reads of the product domain (CR-21), behind `api.py`.

Phase 1 builds the catalogue's shape and the reads. The writes — create, set
status, delete through the event — come with the Productbeheer screens and the
deletion flow of the commits that follow.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.domains.product.models import Product, ProductStatus, ProductVariant


def get_product(db: Session, product_id: int) -> Product | None:
    """The product, or None."""
    return db.get(Product, product_id)


def list_products(db: Session, active_only: bool = False) -> list[Product]:
    """The tenant's products, by name. `active_only` keeps only the ones on sale
    — the public catalogue's view (F16)."""
    query = db.query(Product).order_by(Product.name, Product.id)
    if active_only:
        query = query.filter(Product.status == ProductStatus.ON_SALE)
    return query.all()


def get_variant(db: Session, variant_id: int) -> ProductVariant | None:
    """One variant, or None."""
    return db.get(ProductVariant, variant_id)


def variants_of(db: Session, product_id: int) -> list[ProductVariant]:
    """The variants of a product, in their sort order."""
    return (
        db.query(ProductVariant)
        .filter(ProductVariant.product_id == product_id)
        .order_by(ProductVariant.sort_order, ProductVariant.id)
        .all()
    )


def is_on_sale(db: Session, product_id: int) -> bool:
    """Is the article on sale? (F16: the Webshop offers an article ON_SALE.)"""
    product = get_product(db, product_id)
    return product is not None and product.status is ProductStatus.ON_SALE


def pre_order_window(product: Product, on: date) -> tuple[bool, date | None]:
    """The article's pre-order window on `on` (R39): open while `pre_order` is
    set and `on` is at or before `pre_order_until` — no end date means it stays
    open. Returns `(open, until)`."""
    open_ = bool(product.pre_order) and (
        product.pre_order_until is None or on <= product.pre_order_until
    )
    return open_, product.pre_order_until

"""The reads of the product domain (CR-21), behind `api.py`.

Phase 1 builds the catalogue's shape, the reads, and the delete: a product — or
one of its sizes — without stock movements and without order lines can be
deleted, and `pricing` drops its prices in the same transaction (Q75). The
Productbeheer screens come with the commits that follow.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.domains.product.models import (
    Product,
    ProductAttachment,
    ProductError,
    ProductStatus,
    ProductVariant,
)
from app.domains.stock.api import has_movements
from app.kernel.contracts.media import RemoveAsset
from app.kernel.contracts.product import ProductDeleted
from app.kernel.events import publish
from app.kernel.ports import call


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


def references_to_media(db: Session, asset_ids) -> dict[int, list]:
    """The products that show these pictures, per asset id (CR-15 §C4.4, #1471).

    Media's "where used" hook asks this: a product holds a picture by its media
    asset id, through `ProductAttachment`.
    """
    from app.domains.media.api import MediaUse

    wanted = {int(i) for i in asset_ids}
    if not wanted:
        return {}
    found: dict[int, list] = {}
    rows = (
        db.query(ProductAttachment.media_asset_id, Product.name, Product.id)
        .join(Product, ProductAttachment.product_id == Product.id)
        .filter(ProductAttachment.media_asset_id.in_(wanted))
        .all()
    )
    for asset_id, name, product_id in rows:
        found.setdefault(asset_id, []).append(
            MediaUse(label=f"Artikel {name}", href=f"/admin/producten/{product_id}")
        )
    return found


def delete_product(db: Session, product_id: int) -> None:
    """Delete a product and its sizes, its prices going with them (Q75).

    Refused while the product has stock movements — such an article is set
    DISCONTINUED, never deleted. The order-line gate joins in phase 2, when
    `sales` exists. The files of the product's attachments are removed through
    media's `RemoveAsset` port, but only when no other attachment points at
    them. Publishes `ProductDeleted` inside the transaction, so a refusal in
    `pricing` rolls the delete back.
    """
    product = db.get(Product, product_id)
    if product is None:
        return
    variant_ids = tuple(variant.id for variant in product.variants)
    if has_movements(db, variant_ids):
        from app.i18n import _

        raise ProductError(
            _(
                "Dit artikel heeft voorraadbewegingen en kan niet verwijderd worden — zet het afgevoerd."
            )
        )
    _release_unshared_assets(db, product.attachments)
    publish(ProductDeleted(product_id=product_id, variant_ids=variant_ids, product_gone=True), db)
    db.delete(product)


def delete_variant(db: Session, variant_id: int) -> None:
    """Delete one size of a product, its prices going with it (Q75).

    The product and its own price stay; only the size's prices go. Refused while
    the size has stock movements.
    """
    variant = db.get(ProductVariant, variant_id)
    if variant is None:
        return
    if has_movements(db, (variant_id,)):
        from app.i18n import _

        raise ProductError(_("Deze maat heeft voorraadbewegingen en kan niet verwijderd worden."))
    publish(
        ProductDeleted(
            product_id=variant.product_id, variant_ids=(variant_id,), product_gone=False
        ),
        db,
    )
    db.delete(variant)


def _release_unshared_assets(db: Session, attachments: list[ProductAttachment]) -> None:
    """Remove the media files of the attachments that nothing else shows.

    With no branch in the library nobody reaches a product's file there, so a
    deleted article would leave the bytes stored for good unless the product
    asks the port. `RemoveAsset` does not ask whether the file is still shown,
    so the product removes a file only when no other attachment points at it.
    """
    if not attachments:
        return
    attachment_ids = [attachment.id for attachment in attachments]
    asset_ids = [attachment.media_asset_id for attachment in attachments]
    still_used = {
        row[0]
        for row in db.query(ProductAttachment.media_asset_id)
        .filter(
            ProductAttachment.media_asset_id.in_(asset_ids),
            ProductAttachment.id.notin_(attachment_ids),
        )
        .all()
    }
    for asset_id in set(asset_ids) - still_used:
        call(RemoveAsset(asset_id=asset_id), db)

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
from app.kernel.contracts.media import RemoveAsset
from app.kernel.contracts.product import ProductDeleted
from app.kernel.events import has_subscribers, publish
from app.kernel.ports import call


def get_product(db: Session, product_id: int) -> Product | None:
    """The product, or None."""
    return db.get(Product, product_id)


def create_product(db: Session, name: str) -> Product:
    """Create an article with a name; it starts as Concept (Q74). The sizes,
    prices and pictures come later, on the article record."""
    from app.i18n import _

    name = (name or "").strip()
    if not name:
        raise ProductError(_("Geef het artikel een naam."))
    product = Product(name=name)
    db.add(product)
    db.flush()
    db.commit()
    return product


def update_product(db: Session, product_id: int, *, name: str, description: str | None) -> Product:
    """Change an article's name and description (Q1: the article is what it is)."""
    from app.i18n import _

    product = get_product(db, product_id)
    if product is None:
        raise ProductError(_("Dit artikel bestaat niet."))
    name = (name or "").strip()
    if not name:
        raise ProductError(_("Geef het artikel een naam."))
    product.name = name
    product.description = (description or "").strip() or None
    db.flush()
    return product


def set_status(db: Session, product_id: int, status: ProductStatus) -> Product:
    """Move an article along its life cycle. The aggregate's `check()` refuses a
    walk back to Concept; the allowed changes are the ones of Q74."""
    from app.i18n import _

    product = get_product(db, product_id)
    if product is None:
        raise ProductError(_("Dit artikel bestaat niet."))
    product.status = status
    db.flush()
    db.commit()
    return product


def set_pre_order(
    db: Session, product_id: int, *, pre_order: bool, pre_order_until: date | None
) -> Product:
    """Switch "Op bestelling" on or off, with its last day (R39)."""
    from app.i18n import _

    product = get_product(db, product_id)
    if product is None:
        raise ProductError(_("Dit artikel bestaat niet."))
    product.pre_order = pre_order
    product.pre_order_until = pre_order_until
    db.flush()
    return product


def add_variant(db: Session, product_id: int, size: str) -> ProductVariant:
    """Add one size to an article. The size is the variant's one property
    (`[{"name": "Maat", "value": …}]`, B3a). Flush only: the door commits."""
    from app.i18n import _

    size = (size or "").strip()
    if not size:
        raise ProductError(_("Geef de maat een naam."))
    product = get_product(db, product_id)
    if product is None:
        raise ProductError(_("Dit artikel bestaat niet."))
    variant = ProductVariant(
        product_id=product_id,
        properties=[{"name": "Maat", "value": size}],
        sort_order=len(product.variants),
    )
    db.add(variant)
    db.flush()
    return variant


def rename_variant(db: Session, variant_id: int, size: str) -> ProductVariant:
    """Rename a size: the variant's one `Maat` property gets a new value. Flush
    only: the door commits."""
    from app.i18n import _

    size = (size or "").strip()
    if not size:
        raise ProductError(_("Geef de maat een naam."))
    variant = get_variant(db, variant_id)
    if variant is None:
        raise ProductError(_("Deze maat bestaat niet."))
    variant.properties = [{"name": "Maat", "value": size}]
    db.flush()
    return variant


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
    DISCONTINUED, never deleted. The gate lives in `stock`'s handler on
    `ProductDeleted`, not here: the product does not know its movements. The
    order-line gate joins in phase 2, when `sales` exists. The files of the
    product's attachments are removed through media's `RemoveAsset` port, but
    only when no other attachment points at them. Publishes `ProductDeleted`
    inside the transaction, so a refusal in `pricing` or `stock` rolls the
    delete back.
    """
    product = db.get(Product, product_id)
    if product is None:
        return
    variant_ids = tuple(variant.id for variant in variants_of(db, product_id))
    if not has_subscribers(ProductDeleted):
        raise RuntimeError(
            "nothing subscribes to ProductDeleted; import pricing.handlers and stock.handlers"
        )
    _release_unshared_assets(db, product.attachments)
    publish(ProductDeleted(product_id=product_id, variant_ids=variant_ids, product_gone=True), db)
    db.delete(product)
    db.flush()
    db.commit()


def delete_variant(db: Session, variant_id: int) -> None:
    """Delete one size of a product, its prices going with it (Q75).

    The product and its own price stay; only the size's prices go. Refused while
    the size has stock movements — the gate lives in `stock`'s handler. Flush
    only: the door commits.
    """
    variant = db.get(ProductVariant, variant_id)
    if variant is None:
        return
    if not has_subscribers(ProductDeleted):
        raise RuntimeError(
            "nothing subscribes to ProductDeleted; import pricing.handlers and stock.handlers"
        )
    publish(
        ProductDeleted(
            product_id=variant.product_id, variant_ids=(variant_id,), product_gone=False
        ),
        db,
    )
    db.delete(variant)
    db.flush()


def size_of(variant: ProductVariant) -> str:
    """The size of a variant, from its one `Maat` property (B3a)."""
    for prop in variant.properties or []:
        if prop.get("name") == "Maat":
            return str(prop.get("value", ""))
    return ""


def sync_variants(db: Session, product_id: int, ordered: list[tuple[str, str]]) -> None:
    """Bring the article's sizes to `ordered` — a list of `(key, name)` from the
    record's repeating group. A key that is an existing variant's id renames it, a
    new key adds a size, and an existing variant not in the list is deleted. One
    transaction: a refusal in a delete (a size with movements, through `stock`'s
    handler) rolls every change of this save back.
    """
    existing = {str(variant.id): variant for variant in variants_of(db, product_id)}
    kept: set[str] = set()
    for key, name in ordered:
        name = (name or "").strip()
        if key in existing:
            if name != size_of(existing[key]):
                rename_variant(db, existing[key].id, name)
            kept.add(key)
        elif name:
            add_variant(db, product_id, name)
    for key in list(existing):
        if key not in kept:
            delete_variant(db, existing[key].id)
    db.commit()


def attachments_of(db: Session, product_id: int) -> list[ProductAttachment]:
    """The article's attachments, in their sort order."""
    return (
        db.query(ProductAttachment)
        .filter(ProductAttachment.product_id == product_id)
        .order_by(ProductAttachment.sort_order, ProductAttachment.id)
        .all()
    )


def attachment_cards(db: Session, product_id: int) -> list[dict]:
    """What the record shows: each attachment with `is_photo` and its media id, so
    the screen tells a picture from a document without comparing a code."""
    from app.domains.media.api import MediaAsset, MediaKind

    attachments = attachments_of(db, product_id)
    ids = [attachment.media_asset_id for attachment in attachments]
    kinds = (
        {asset.id: asset.kind for asset in db.query(MediaAsset).filter(MediaAsset.id.in_(ids))}
        if ids
        else {}
    )
    return [
        {
            "id": attachment.id,
            "media_asset_id": attachment.media_asset_id,
            "title": attachment.title,
            "is_photo": kinds.get(attachment.media_asset_id) == MediaKind.PRODUCT_PHOTO,
        }
        for attachment in attachments
    ]


def add_attachment(
    db: Session,
    product_id: int,
    *,
    kind: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> ProductAttachment:
    """Upload a picture or a document on the article (R3): the bytes go to media
    through `StoreFile`, the article holds the soft reference. One transaction —
    the door commits. A file that is not there is refused here, so every entrance
    meets the rule."""
    from app.i18n import _
    from app.kernel.contracts.media import StoreFile
    from app.kernel.ports import call

    if not filename or not content:
        raise ProductError(_("Kies een bestand."))
    stored = call(
        StoreFile(kind=kind, filename=filename, content_type=content_type, content=content),
        db,
    )
    attachment = ProductAttachment(
        product_id=product_id,
        media_asset_id=stored.asset_id,
        sort_order=len(attachments_of(db, product_id)),
    )
    db.add(attachment)
    db.flush()
    db.commit()
    return attachment


def remove_attachment(db: Session, attachment_id: int) -> None:
    """Remove one attachment and its file (through media's `RemoveAsset`)."""
    from app.kernel.contracts.media import RemoveAsset
    from app.kernel.ports import call

    attachment = db.get(ProductAttachment, attachment_id)
    if attachment is None:
        return
    call(RemoveAsset(asset_id=attachment.media_asset_id), db)
    db.delete(attachment)
    db.flush()
    db.commit()


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

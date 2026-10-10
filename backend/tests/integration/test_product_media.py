"""A product's two media kinds (CR-21, phase 1): the photo is re-encoded, the
document is kept byte-equal, and the product joins media's "where used".

`product_photo` is uploaded on the article and re-encoded like every image;
`product_document` is a size chart or the like, kept lossless. Neither appears
in the library's tree or the picker. A picture a product shows is counted by
`uses_of`, and deleting it through the library is refused, naming the product.
"""

from __future__ import annotations

import pytest

from app.domains.media.api import MediaAsset, MediaInUse, MediaKind, delete_media, uses_of
from app.domains.product.api import Product, ProductAttachment
from app.kernel.contracts.media import StoreFile
from app.kernel.ports import call
from tests.integration.test_designstudio_engine import PNG_2x2

pytestmark = pytest.mark.ui_agnostisch

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _product(db) -> Product:
    product = Product(name="T-shirt Raak")
    db.add(product)
    db.flush()
    return product


def test_a_product_photo_is_stored_and_reencoded(db_session):
    _product(db_session)
    outcome = call(
        StoreFile(
            kind="product_photo",
            filename="t-shirt.png",
            content_type="image/png",
            content=PNG_2x2,
        ),
        db_session,
    )
    asset = db_session.get(MediaAsset, outcome.asset_id)
    assert asset.kind is MediaKind.PRODUCT_PHOTO
    assert asset.content_type in ("image/png", "image/jpeg")
    assert asset.data != PNG_2x2, "a photo is re-encoded, never stored raw"


def test_a_product_document_pdf_is_kept_byte_equal(db_session):
    _product(db_session)
    outcome = call(
        StoreFile(
            kind="product_document",
            filename="maattabel.pdf",
            content_type="application/pdf",
            content=MINIMAL_PDF,
        ),
        db_session,
    )
    asset = db_session.get(MediaAsset, outcome.asset_id)
    assert asset.kind is MediaKind.PRODUCT_DOCUMENT
    assert asset.data == MINIMAL_PDF, "a document is kept byte-equal"


def _attachment(db, kind: str = "product_photo") -> tuple[Product, MediaAsset]:
    product = _product(db)
    asset = MediaAsset(kind=kind, data=b"x", content_type="image/png")
    db.add(asset)
    db.flush()
    db.add(ProductAttachment(product_id=product.id, media_asset_id=asset.id))
    db.flush()
    return product, asset


def test_where_used_names_the_product(db_session):
    product, asset = _attachment(db_session)

    uses = uses_of(db_session, asset.id)
    assert [(u.label, u.href) for u in uses] == [
        (f"Artikel {product.name}", f"/admin/producten/{product.id}")
    ]


def test_removing_an_asset_a_product_shows_is_refused(db_session):
    product, asset = _attachment(db_session)

    with pytest.raises(MediaInUse) as refused:
        delete_media(db_session, asset.id)
    assert f"Artikel {product.name}" in str(refused.value)

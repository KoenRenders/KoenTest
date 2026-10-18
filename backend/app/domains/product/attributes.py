"""The attributes of the `product` domain: every business column of its tables (CR-33).

Generated once from the ORM and the rules of the inventory, then kept by hand like
`codes.py`. `label` is filled where a screen shows the datum; the comment after the
classification names the rule of the inventory that decided it.
"""

from app.kernel.attributes import AiExposure, Attribute

ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute(
        key="product.product.name",
        columns=("product.products.name",),
        label="Naam",
        name_en="Name",
        help="De naam van het artikel.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="product.product.description",
        columns=("product.products.description",),
        label="Omschrijving",
        name_en="Description",
        help="De beschrijving van het artikel.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="product.product.status",
        columns=("product.products.status",),
        label="Status",
        name_en="Status",
        help="Concept, In verkoop of Afgevoerd.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="product.product.pre_order",
        columns=("product.products.pre_order",),
        label="Op bestelling",
        name_en="Pre order",
        help="Het artikel is op bestelling bestelbaar, ook zonder voorraad.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="product.product.pre_order_until",
        columns=("product.products.pre_order_until",),
        label="Bestellen tot en met",
        name_en="Pre order until",
        help="Tot wanneer het artikel op bestelling bestelbaar is.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="product.product_variant.properties",
        columns=("product.product_variants.properties",),
        label="Maat",
        name_en="Properties",
        help="De eigenschappen van de maat, als JSON.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="product.product_variant.sku",
        columns=("product.product_variants.sku",),
        label=None,
        name_en="Sku",
        help="De interne code van de maat.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="product.product_variant.sort_order",
        columns=("product.product_variants.sort_order",),
        label=None,
        name_en="Sort order",
        help="De volgorde van de maat binnen het artikel.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="product.product_attachment.description",
        columns=("product.product_attachments.description",),
        label="Beschrijving",
        name_en="Description",
        help="De alt-tekst van een foto van het artikel.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="product.product_attachment.title",
        columns=("product.product_attachments.title",),
        label="Titel",
        name_en="Title",
        help="De titel van een document van het artikel.",
        ai_exposure=AiExposure.PUBLIC,  # K5
    ),
    Attribute(
        key="product.product_attachment.media_asset_id",
        columns=("product.product_attachments.media_asset_id",),
        label=None,
        name_en="Media asset id",
        help="Het mediabestand dat bij het artikel hangt.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
    Attribute(
        key="product.product_attachment.sort_order",
        columns=("product.product_attachments.sort_order",),
        label=None,
        name_en="Sort order",
        help="De volgorde van de bijlagen van het artikel.",
        ai_exposure=AiExposure.INTERNAL,  # K0
    ),
)

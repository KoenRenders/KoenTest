"""Public facade of the product domain (CR-21).

Everything another module may use lives here. The ORM classes are exported for
other domains' services, not for screens; the layer gate holds that line.
"""

from app.domains.product.codes import PRODUCT_STATUS  # noqa: F401
from app.domains.product.models import (  # noqa: F401
    Product,
    ProductAttachment,
    ProductError,
    ProductStatus,
    ProductVariant,
)
from app.domains.product.service import (  # noqa: F401
    add_variant,
    create_product,
    delete_product,
    delete_variant,
    get_product,
    get_variant,
    is_on_sale,
    list_products,
    pre_order_window,
    references_to_media,
    set_pre_order,
    set_status,
    update_product,
    variants_of,
)


def size_of(variant: ProductVariant) -> str:
    """The size of a variant, from its one `Maat` property (B3a)."""
    for prop in variant.properties or []:
        if prop.get("name") == "Maat":
            return str(prop.get("value", ""))
    return ""


__all__ = [
    "PRODUCT_STATUS",
    "Product",
    "ProductAttachment",
    "ProductError",
    "ProductStatus",
    "ProductVariant",
    "add_variant",
    "create_product",
    "delete_product",
    "delete_variant",
    "get_product",
    "get_variant",
    "is_on_sale",
    "list_products",
    "pre_order_window",
    "references_to_media",
    "set_pre_order",
    "set_status",
    "size_of",
    "update_product",
    "variants_of",
]

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
    delete_product,
    delete_variant,
    get_product,
    get_variant,
    is_on_sale,
    list_products,
    pre_order_window,
    references_to_media,
    variants_of,
)

__all__ = [
    "PRODUCT_STATUS",
    "Product",
    "ProductAttachment",
    "ProductError",
    "ProductStatus",
    "ProductVariant",
    "delete_product",
    "delete_variant",
    "get_product",
    "get_variant",
    "is_on_sale",
    "list_products",
    "pre_order_window",
    "references_to_media",
    "variants_of",
]

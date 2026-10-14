"""Public facade of the sales domain (CR-21, the webshop).

Everything another module may use lives here. The ORM classes are exported for
other domains' services, not for screens; the layer gate holds that line.
"""

from app.domains.sales.models import (  # noqa: F401
    ProductHasOrderLines,
    SalesError,
    SalesOrder,
    SalesOrderLine,
    ShopContact,
    ShopSettings,
)
from app.domains.sales.payables import order_describer  # noqa: F401
from app.domains.sales.service import (  # noqa: F401
    article_offer,
    basket_lines,
    get_order,
    offered_products,
    orders_of_person,
    owned_order,
    place_order,
    submit_order,
    total_of,
)

__all__ = [
    "ProductHasOrderLines",
    "SalesError",
    "SalesOrder",
    "SalesOrderLine",
    "ShopContact",
    "ShopSettings",
    "article_offer",
    "basket_lines",
    "get_order",
    "offered_products",
    "order_describer",
    "orders_of_person",
    "owned_order",
    "place_order",
    "submit_order",
    "total_of",
]

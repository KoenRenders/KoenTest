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
    board_order_person,
    cancel_order,
    deliver_line,
    get_order,
    list_orders,
    offered_products,
    order_delivery_state,
    order_payment_state,
    order_view,
    orders_of_person,
    owned_order,
    parse_items,
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
    "board_order_person",
    "cancel_order",
    "deliver_line",
    "get_order",
    "list_orders",
    "offered_products",
    "order_delivery_state",
    "order_describer",
    "order_payment_state",
    "order_view",
    "orders_of_person",
    "owned_order",
    "parse_items",
    "place_order",
    "submit_order",
    "total_of",
]

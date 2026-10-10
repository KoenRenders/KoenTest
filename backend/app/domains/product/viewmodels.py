"""View-models of the product screens (CR-21)."""

from dataclasses import dataclass, field
from typing import Any, Optional

from app.domains.product.models import Product
from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class ProductListView(ViewModel):
    """`admin_producten.html` and its fragment `_producten_lijst.html`."""

    products: list[Product]
    # How many sizes each product has, for the "n maten" line of a card.
    sizes: dict[int, int]
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class ProductNewView(ViewModel):
    """`admin_product_nieuw.html`."""

    csrf_token: str
    error: Optional[str] = None
    nav_items: list[dict[str, Any]] = field(default_factory=list)
